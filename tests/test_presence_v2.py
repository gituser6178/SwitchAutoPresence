"""Offline tests for the v0.2 automatic/manual Rich Presence prototype."""
import numpy as np
import pytest

from switchautopresence.artwork import ArtworkCatalog
from switchautopresence.catalog import GameCatalog
from switchautopresence.cli import make_parser
from switchautopresence.discord_presence import DiscordPublisher
from switchautopresence.recognition import FrameKind, HomeRecognizer, looks_like_home, parse_roi
from switchautopresence.runtime import Runtime
from switchautopresence.settings import load_artwork, load_mode, save_mode
from switchautopresence.state import Activity, Mode, Screen, Session
from switchautopresence.window_capture import WindowCapture


def session():
    return Session(clock=lambda: 123456)


def test_highlighted_home_tile_not_playing():
    s = session()
    s.home("The Legend of Zelda: Ocarina of Time")
    assert s.snapshot().activity.details == "Browsing HOME"
    assert s.snapshot().activity.game is None


def test_home_requires_launch_transition():
    s = session()
    s.home("Pokémon Violet")
    s.non_home()
    s.non_home()
    assert s.snapshot().confirmed is None
    assert s.snapshot().activity.details == "Launching game"
    s.non_home()
    assert s.snapshot().confirmed == "Pokémon Violet"
    assert s.snapshot().activity.started_at == 123456


def test_starting_in_game_cannot_guess_title():
    s = session()
    s.non_home()
    assert s.snapshot().screen == Screen.UNKNOWN
    assert s.snapshot().activity.game is None


def test_unknown_home_title_never_claims_other_game():
    s = session()
    s.home(None)
    for _ in range(3):
        s.non_home()
    assert s.snapshot().screen == Screen.UNKNOWN
    assert s.snapshot().activity.game is None


def test_return_to_home_resets_playing_claim():
    s = session()
    s.home("Pokémon Violet")
    for _ in range(3):
        s.non_home()
    s.home("Mario Kart World")
    assert s.snapshot().confirmed is None
    assert s.snapshot().activity.details == "Browsing HOME"


def test_manual_wins_over_auto_capture():
    s = session()
    s.set_manual("Mario Kart World")
    s.home("Pokémon Violet")
    for _ in range(4):
        s.non_home()
    assert s.snapshot().activity.game == "Mario Kart World"
    assert s.snapshot().mode == Mode.MANUAL


def test_manual_works_with_no_capture():
    s = session()
    s.set_manual("  Dragon Quest  XI  ")
    assert s.snapshot().activity.game == "Dragon Quest XI"


@pytest.mark.parametrize("title", ["", "   ", "x" * 129])
def test_invalid_manual_title(title):
    with pytest.raises(ValueError):
        session().set_manual(title)


def test_clear_persists_until_user_reenables():
    s = session()
    s.set_manual("Pokémon Violet")
    s.clear()
    s.home("Mario Kart World")
    assert s.snapshot().activity is None
    s.resume_auto()
    assert s.snapshot().screen == Screen.WAITING
    assert s.snapshot().activity is None


def test_no_signal_disables_auto_not_manual():
    s = session()
    s.home("Pokémon Violet")
    s.no_signal()
    assert s.snapshot().activity is None
    s.set_manual("Pokémon Violet")
    s.no_signal()
    assert s.snapshot().activity.game == "Pokémon Violet"


def test_same_manual_title_preserves_timer():
    now = [10]
    s = Session(clock=lambda: now[0])
    s.set_manual("Pokémon Violet")
    now[0] = 999
    s.set_manual("Pokémon Violet")
    assert s.snapshot().activity.started_at == 10
    s.set_manual("Mario Kart World")
    assert s.snapshot().activity.started_at == 999


def test_catalog_fuzzy_accents_and_punctuation():
    c = GameCatalog()
    assert c.match("POKEMON violet") == "Pokémon Violet"
    assert c.match("The Legend of Zelda: Ocarina of Time") == "The Legend of Zelda: Ocarina of Time"


@pytest.mark.parametrize("garbage", ["Ocarina", "Your shield is broken!", "Zelda Breath of"])
def test_catalog_doesnt_guess_unrelated_text(garbage):
    assert GameCatalog().match(garbage) is None


def test_artwork_fallback_and_custom():
    art = ArtworkCatalog(generic="switch", small="console", games={"Pokémon Violet": "https://example.com/violet.png"})
    assert art.resolve("Pokémon Violet").large_image.endswith("violet.png")
    assert art.resolve("Unknown").large_image == "switch"
    assert art.resolve("Pokémon Violet").small_image == "console"


@pytest.mark.parametrize("image", [
    "http://example.com/game.png", "file:///C:/private.png",
    "https://user:pass@example.com/img.png", r"C:\private", "bad path"
])
def test_artwork_ref_rejects_insecure_sources(image):
    with pytest.raises(ValueError):
        ArtworkCatalog(generic=image)


class FakeRPC:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []
    def connect(self):
        self.calls.append(("connect",))
        if self.fail:
            raise OSError("Discord not running")
    def update(self, **kwargs):
        self.calls.append(("update", kwargs))
    def clear(self):
        self.calls.append(("clear",))
    def close(self):
        self.calls.append(("close",))


def test_discord_sends_name_image_timestamp_and_dedupes():
    rpc = FakeRPC()
    now = [100]
    publisher = DiscordPublisher(
        "123", ArtworkCatalog(generic="switch", games={"Pokémon Violet": "https://example.com/violet.png"}),
        rpc_factory=lambda _: rpc, clock=lambda: now[0]
    )
    game = Activity(details="Playing Pokémon Violet", game="Pokémon Violet", started_at=555)
    assert publisher.sync(game)
    payload = rpc.calls[-1][1]
    assert payload["name"] == "Nintendo Switch"
    assert payload["large_image"].endswith("violet.png")
    assert payload["start"] == 555
    assert publisher.sync(game)
    assert len([call for call in rpc.calls if call[0] == "update"]) == 1
    now[0] = 150
    publisher.sync(game)
    assert len([call for call in rpc.calls if call[0] == "update"]) == 2
    publisher.sync(None)
    assert rpc.calls[-1][0] == "clear"


def test_discord_home_art_is_generic():
    pub = DiscordPublisher("123", ArtworkCatalog(generic="switch"))
    assert pub.preview(Activity(details="Browsing HOME"))["large_image"] == "switch"


def test_discord_without_app_id_is_dry_run():
    pub = DiscordPublisher(None, ArtworkCatalog(), rpc_factory=lambda _: (_ for _ in ()).throw(RuntimeError()))
    assert not pub.sync(Activity(details="Browsing HOME"))
    assert "Dry run" in pub.error


def test_discord_reconnects_after_failure():
    now = [0]
    clients = [FakeRPC(fail=True), FakeRPC()]
    pub = DiscordPublisher("123", ArtworkCatalog(), rpc_factory=lambda _: clients.pop(0), clock=lambda: now[0])
    assert not pub.sync(Activity(details="Browsing HOME"))
    now[0] = 5
    assert not pub.sync(Activity(details="Browsing HOME"))
    now[0] = 11
    assert pub.sync(Activity(details="Browsing HOME"))


@pytest.mark.parametrize("roi", ["0,0,1,1,1", "a,b,c,d", "0.8,0,0.8,0.1", "0,0,0,1"])
def test_reject_bad_ocr_region(roi):
    with pytest.raises(ValueError):
        parse_roi(roi)


def home_image():
    image = np.full((600, 1000, 3), 119, dtype=np.uint8)
    image[240:450, 260:720] = (15, 160, 100)
    return image


class StubOCR:
    def __init__(self, words, scores):
        self.words = words
        self.scores = scores
        self.calls = []
    def __call__(self, image):
        self.calls.append(image.shape)
        return type("O", (), {"txts": self.words, "scores": self.scores})()


def test_home_ocr_reads_game_title_but_does_not_claim_launch():
    ocr = StubOCR(["The Legend of Zelda:", "Ocarina of Time"], [.97, .96])
    assert looks_like_home(home_image())
    result = HomeRecognizer(GameCatalog(), engine=ocr).analyze(home_image())
    assert result.kind == FrameKind.HOME
    assert result.title == "The Legend of Zelda: Ocarina of Time"
    assert ocr.calls


def test_gameplay_doesnt_trigger_home_ocr():
    ocr = StubOCR(["Pokemon Violet"], [.95])
    gameplay = np.full((600, 1000, 3), (15, 220, 70), dtype=np.uint8)
    assert HomeRecognizer(GameCatalog(), engine=ocr).analyze(gameplay).kind == FrameKind.OTHER
    assert ocr.calls == []


def test_dark_scene_not_considered_launch():
    image = np.zeros((600, 1000, 3), dtype=np.uint8)
    assert HomeRecognizer(GameCatalog(), engine=StubOCR([], [])).analyze(image).kind == FrameKind.DARK


def test_unknown_selected_game_stays_home():
    result = HomeRecognizer(GameCatalog(), engine=StubOCR(["Unlisted Game"], [.98])).analyze(home_image())
    assert result.kind == FrameKind.HOME
    assert result.title is None


class FakeControl:
    def __init__(self):
        self.stopped = False
    def stop(self):
        self.stopped = True


class FakeWGC:
    instance = None
    def __init__(self, **kwargs):
        self.options = kwargs
        self.callbacks = {}
        self.control = FakeControl()
        FakeWGC.instance = self
    def event(self, handler):
        self.callbacks[handler.__name__] = handler
    def start_free_threaded(self):
        return self.control
    def emit(self, frame):
        self.callbacks["on_frame_arrived"](type("Frame", (), {"frame_buffer": frame})(), None)


def test_window_capture_frames_are_sampled_and_copied():
    now = [1]
    src = WindowCapture("VideoGameCapture", interval_seconds=1, capture_class=FakeWGC, clock=lambda: now[0])
    src.start()
    raw = np.full((100, 200, 4), 50, dtype=np.uint8)
    FakeWGC.instance.emit(raw)
    result = src.poll()
    assert result[1].shape == (100, 200, 3)
    raw[:] = 0
    assert np.mean(result[1]) == 50
    FakeWGC.instance.emit(raw)
    assert src.poll() is None
    now[0] = 3
    FakeWGC.instance.emit(raw)
    assert src.poll() is not None
    src.stop()
    assert FakeWGC.instance.control.stopped


def test_viewer_close_event():
    src = WindowCapture("Viewer", capture_class=FakeWGC)
    src.start()
    FakeWGC.instance.callbacks["on_closed"]()
    assert src.closed
    src.stop()


class FakePublisher:
    error = None
    def sync(self, activity):
        return True
    def close(self):
        pass


class FakeClassifier:
    def __init__(self, kind, title=None):
        self.kind, self.title = kind, title
    def analyze(self, _):
        from switchautopresence.recognition import Recognition
        return Recognition(self.kind, self.title)


def runtime(tmp_path):
    return Runtime(publisher=FakePublisher(), settings_file=tmp_path / "settings.json", artwork_file=tmp_path / "artwork.json")


def test_runtime_observes_home_to_playing_and_dark_grace(tmp_path):
    app = runtime(tmp_path)
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    app.recognizer = FakeClassifier(FrameKind.HOME, "Pokémon Violet")
    app._observe(frame)
    assert app.session.snapshot().activity.details == "Browsing HOME"
    app.recognizer = FakeClassifier(FrameKind.OTHER)
    for _ in range(3):
        app._observe(frame)
    assert app.session.snapshot().confirmed == "Pokémon Violet"
    app.recognizer = FakeClassifier(FrameKind.DARK)
    for _ in range(3):
        app._observe(frame)
    assert app.session.snapshot().confirmed == "Pokémon Violet"
    app._observe(frame)
    assert app.session.snapshot().activity is None


def test_runtime_manual_title_and_artwork_persist(tmp_path):
    app = runtime(tmp_path)
    app.select_manual("Pokémon Violet", "https://example.com/pokemon.png")
    assert load_mode(tmp_path / "settings.json") == (Mode.MANUAL, "Pokémon Violet")
    assert load_artwork(tmp_path / "artwork.json")["pokémon violet"].endswith("pokemon.png")
    copy = runtime(tmp_path)
    assert copy.session.snapshot().activity.game == "Pokémon Violet"
    assert copy.artwork.resolve("Pokémon Violet").large_image.endswith("pokemon.png")
    copy.clear()
    assert copy.session.snapshot().activity is None


def test_invalid_manual_art_does_not_change_game(tmp_path):
    app = runtime(tmp_path)
    app.select_manual("Pokémon Violet")
    with pytest.raises(ValueError):
        app.select_manual("Mario Kart World", "http://example.com/image.jpg")
    assert app.session.snapshot().activity.game == "Pokémon Violet"


def test_resume_auto_requires_fresh_game_detection(tmp_path):
    app = runtime(tmp_path)
    app.select_manual("Pokémon Violet")
    app.select_auto()
    assert app.session.snapshot().screen == Screen.WAITING
    assert app.session.snapshot().activity is None


def test_invalid_local_prefs_fail_safe(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    assert load_mode(path) == (Mode.AUTO, None)


def test_cli_has_old_and_new_commands():
    parser = make_parser()
    assert parser.parse_args(["probe", "--device", "1"]).backend == "dshow"
    assert parser.parse_args(["windows"]).command == "windows"
    assert parser.parse_args(["probe-window", "--seconds", "10"]).seconds == 10
    assert parser.parse_args(["scan-window", "--roi", "0.1,0.2,0.7,0.3"]).roi == "0.1,0.2,0.7,0.3"
    assert parser.parse_args(["app", "--app-id", "123"]).app_id == "123"


def test_ocr_temporary_miss_keeps_candidate_before_launch():
    s = session()
    s.home("The Legend of Zelda: Ocarina of Time")
    for _ in range(3):
        s.home(None)
    assert s.snapshot().candidate == "The Legend of Zelda: Ocarina of Time"
    for _ in range(3):
        s.non_home()
    assert s.snapshot().confirmed == "The Legend of Zelda: Ocarina of Time"


def test_many_ocr_misses_expire_candidate_to_prevent_wrong_game():
    s = session()
    s.home("Pokémon Violet")
    for _ in range(4):
        s.home(None)
    assert s.snapshot().candidate is None
    for _ in range(3):
        s.non_home()
    assert s.snapshot().screen == Screen.UNKNOWN


def test_home_selection_change_replaces_candidate():
    s = session()
    s.home("Pokémon Violet")
    s.home(None)
    s.home("Mario Kart World")
    for _ in range(3):
        s.non_home()
    assert s.snapshot().confirmed == "Mario Kart World"


def test_ocr_miss_tolerance_validated():
    with pytest.raises(ValueError):
        Session(ocr_miss_tolerance=-1)


def test_neutral_loading_screen_without_title_is_not_home():
    frame = np.full((600, 1000, 3), 119, dtype=np.uint8)
    result = HomeRecognizer(GameCatalog(), engine=StubOCR([], [])).analyze(frame)
    assert result.kind == FrameKind.OTHER
    assert result.method == "neutral_without_title"


def test_cyan_zelda_title_uses_recognition_only_fallback():
    import cv2
    frame = home_image()
    cv2.putText(
        frame, "The Legend of Zelda: Ocarina of Time", (105, 150),
        cv2.FONT_HERSHEY_SIMPLEX, .75, (235, 222, 85), 2,
    )
    class DirectOCR:
        def __init__(self):
            self.use_det_values = []
        def __call__(self, img, **kwargs):
            self.use_det_values.append(kwargs.get("use_det"))
            return type("R", (), {
                "txts": ("The Legend of Zelda: Ocarina of Time",),
                "scores": (.97,),
            })()
    engine = DirectOCR()
    result = HomeRecognizer(GameCatalog(), engine=engine).analyze(frame)
    assert result.kind == FrameKind.HOME
    assert result.title == "The Legend of Zelda: Ocarina of Time"
    assert result.method == "cyan_line"
    assert engine.use_det_values == [False]


def test_one_false_home_frame_does_not_reset_confirmed_playing(tmp_path):
    app = runtime(tmp_path)
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    app.recognizer = FakeClassifier(FrameKind.HOME, "Pokémon Violet")
    app._observe(frame)
    app.recognizer = FakeClassifier(FrameKind.OTHER)
    for _ in range(3):
        app._observe(frame)
    assert app.session.snapshot().screen == Screen.PLAYING
    app.recognizer = FakeClassifier(FrameKind.HOME)
    app._observe(frame)
    assert app.session.snapshot().screen == Screen.PLAYING
    app._observe(frame)
    assert app.session.snapshot().screen == Screen.HOME


def test_cyan_game_tile_colors_do_not_count_as_home_title():
    frame = home_image()
    # Bright cyan artwork below the title region is NOT title evidence.
    frame[170:220, 200:700] = (235, 222, 85)
    result = HomeRecognizer(GameCatalog(), engine=StubOCR([], [])).analyze(frame)
    assert result.kind == FrameKind.OTHER
    assert result.method == "neutral_without_title"
