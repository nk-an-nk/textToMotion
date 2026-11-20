package jp.ojimalab.kebbi.ui.viewmodel;

import android.app.Application;
import android.net.Uri;
import androidx.lifecycle.AndroidViewModel;
import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import jp.ojimalab.kebbi.AndroidScheduler;
import jp.ojimalab.kebbi.RobotFactory;
import jp.ojimalab.kebbi.core.*;
import jp.ojimalab.kebbi.core.RuntimePorts.Snapshot;
import jp.ojimalab.kebbi.core.RuntimePorts.State;
import jp.ojimalab.kebbi.data.JsonTrace;
import jp.ojimalab.kebbi.data.LatencyStore;
import jp.ojimalab.kebbi.data.MotionStore;
import jp.ojimalab.kebbi.data.SettingsStore;
import jp.ojimalab.kebbi.data.SettingsStore.ConnectionSettings;

/** Handles UI actions on the main thread and publishes screen state for the Activity. */
public final class ConversationViewModel extends AndroidViewModel {
  private static final String DEFAULT_MOCK_INPUT = "Hello, Kebbi!";
  private static final String MAPPING_PENDING = "② 事前分類表: 確認待ち";
  private final MutableLiveData<ConversationUiState> screen = new MutableLiveData<>();
  private final AndroidScheduler scheduler = new AndroidScheduler();
  private final SettingsStore settings;
  private final LatencyStore latency;
  private final JsonTrace trace;
  private final MotionStore motions;
  private ApiClient api;
  private RobotAdapter robot;
  private ConversationController controller;
  private MotionRegistry registry;
  private boolean foreground, mappingRequested, mappingInFlight;
  private long engine;
  private Snapshot turn;
  private List<String> motionNames = Collections.emptyList();
  private String reply = "", lastLoggedTurn = "", error = "", backendStatus = "確認中";
  private String mappingStatus = MAPPING_PENDING;

  public ConversationViewModel(Application application) {
    super(application);
    settings = new SettingsStore(application);
    latency = new LatencyStore(application);
    trace = new JsonTrace(application, settings);
    motions = new MotionStore(application, settings);
    publish();
  }

  public LiveData<ConversationUiState> screen() {
    return screen;
  }

  public boolean isRealDevice() {
    return RobotFactory.REAL;
  }

  public void onStart() {
    foreground = true;
    startEngine();
  }

  public void onStop() {
    foreground = false;
    endEngine();
  }

  @Override
  protected void onCleared() {
    onStop();
    super.onCleared();
  }

  private void startEngine() {
    if (!foreground || controller != null) return;
    long current = ++engine;
    turn = null;
    reply = "";
    backendStatus = "確認中";
    mappingStatus = MAPPING_PENDING;
    mappingRequested = false;
    mappingInFlight = false;
    String mappingError = "";
    try {
      registry = motions.load();
    } catch (RuntimeException ignored) {
      registry = new MotionRegistry();
      mappingError = "モーション設定が不正です。管理画面で設定し直してください。";
    }
    ConnectionSettings config = settings.connection();
    try {
      api = new ApiClient(config.url, config.token);
    } catch (RuntimeException ignored) {
      error = "API URLが不正です。設定を修正してください。";
      backendStatus = "未接続";
      publish();
      return;
    }
    robot = RobotFactory.create(getApplication(), scheduler);
    configureMock(DEFAULT_MOCK_INPUT);
    controller = new ConversationController(robot, robot, robot, api, scheduler,
        (turnId, event, fields) -> {
          if ("metrics".equals(event)) {
            latency.record(turnId, fields);
            if (isCurrent(current)) publish();
          }
          trace.event(turnId, event, fields);
        },
        snapshot -> {
          if (isCurrent(current)) receive(snapshot);
        }, registry);
    controller.settings(config.language, config.motion);
    controller.replyModel(settings.replyModel());
    applyExperiment(settings.experiment());
    controller.connect();
    if (!mappingError.isEmpty()) showError(mappingError);
    checkBackend();
  }

  private void endEngine() {
    engine++;
    try {
      if (controller != null) controller.close();
    } finally {
      if (api != null) api.close();
      controller = null;
      api = null;
      robot = null;
      turn = null;
      motionNames = Collections.emptyList();
      publish();
    }
  }

  private boolean isCurrent(long generation) {
    return generation == engine && foreground;
  }

  private void receive(Snapshot snapshot) {
    turn = snapshot;
    if (!snapshot.speech.isEmpty() || !snapshot.continuous) reply = snapshot.speech;
    error = snapshot.message;
    if (!snapshot.speech.isEmpty() && !snapshot.turnId.equals(lastLoggedTurn)) {
      lastLoggedTurn = snapshot.turnId;
      trace.content(snapshot.turnId, snapshot.text, snapshot.speech);
    }
    Set<String> available = controller.motions();
    if (available.size() != motionNames.size() || !available.containsAll(motionNames)) {
      motionNames = Collections.unmodifiableList(new ArrayList<>(available));
      if (!motionNames.isEmpty()) motions.writeCatalog(motionNames);
    }
    requestMapping();
    publish();
  }

  private void publish() {
    screen.setValue(new ConversationUiState(turn, reply, error, backendStatus, mappingStatus,
        latency.latestText() + (latency.warning().isEmpty() ? "" : "\n" + latency.warning()),
        motionNames, "ja".equals(settings.language()) ? 1 : 0,
        SelectionOptions.REPLY_MODELS.indexOf(settings.replyModel()), settings.experiment()));
  }

  public void submit(String input) {
    if (controller != null) controller.submit(input);
  }

  public void stop() {
    if (controller != null) controller.stop();
  }

  public void newSession() {
    if (controller != null) controller.newSession();
  }

  public void startListening(String mockText, boolean only) {
    if (controller == null) return;
    configureMock(mockText.isEmpty() ? DEFAULT_MOCK_INPUT : mockText);
    if (only) controller.listen(true);
    else controller.startConversation();
  }

  public void testSpeech(String text, Gesture gesture, boolean withMotion) {
    if (controller == null) return;
    configureMock(DEFAULT_MOCK_INPUT);
    controller.testSpeech(text, gesture, withMotion);
  }

  public void testMotion(String id) {
    if (controller == null) return;
    configureMock("");
    controller.testMotion(id);
  }

  private void configureMock(String input) {
    robot.configureMock(input, settings.connection().mockFault);
  }

  public void reconnect() {
    if (controller == null) {
      startEngine();
      return;
    }
    if (controller.state() == State.IDLE) controller.connect();
    checkBackend();
  }

  private void checkBackend() {
    if (api == null) return;
    long current = engine;
    backendStatus = "確認中";
    publish();
    api.health(status -> scheduler.execute(() -> {
      if (isCurrent(current)) {
        backendStatus = status;
        publish();
      }
    }));
  }

  public void showError(String message) {
    error = message;
    publish();
  }

  public ConnectionSettings connectionSettings() {
    return settings.connection();
  }

  /** Returns false for an invalid URL, so the view can keep the settings dialog open. */
  public boolean saveSettings(ConnectionSettings config) {
    try (ApiClient validated = new ApiClient(config.url, "")) {
      // Check the URL with the same parser that will be used for requests.
    } catch (IllegalArgumentException ignored) {
      return false;
    }
    endEngine();
    error = "";
    settings.saveConnection(config);
    startEngine();
    return true;
  }

  public void selectLanguage(int index) {
    String value = index == 1 ? "ja" : "en";
    ConnectionSettings current = settings.connection();
    if (value.equals(current.language) || !canEditConversation()) return;
    settings.setLanguage(value);
    if (controller != null) {
      controller.newSession();
      controller.settings(value, current.motion);
    }
    publish();
  }

  public void selectReplyModel(int index) {
    String value = SelectionOptions.REPLY_MODELS.get(index);
    if (value.equals(settings.replyModel()) || !canEditConversation()) return;
    settings.setReplyModel(value);
    if (controller != null) controller.replyModel(value);
    publish();
  }

  public void selectExperiment(int index) {
    if (index == settings.experiment() || !canEditConversation()) return;
    settings.setExperiment(index);
    if (controller != null) applyExperiment(index);
    publish();
  }

  private boolean canEditConversation() {
    return turn == null || (turn.state == State.IDLE && !turn.continuous);
  }

  private void applyExperiment(int index) {
    controller.experiment(index == 2 ? "direct" : "category", index == 1 ? "expanded" : "basic");
  }

  public String candidateSummary() {
    if (controller == null) return "";
    int condition = settings.experiment();
    Set<String> available = controller.motions();
    long now = scheduler.now();
    List<SelectionOptions.Candidate> candidates = condition == 2
        ? registry.candidates(available, now)
        : registry.categoryCandidates(available, now, condition == 1);
    StringBuilder text = new StringBuilder("現在の候補: " + candidates.size() + "件 / SDK一覧 "
        + available.size() + "件\n①はSDK全動作から選択（クールダウン中を除く）。"
        + "②はLLMがカテゴリを選び、そのカテゴリ内のIDもLLMが選択。\n");
    for (SelectionOptions.Candidate candidate : candidates) {
      text.append("\n").append(candidate.id).append("\n").append(candidate.description)
          .append("\nカテゴリ: ").append(String.join(", ", candidate.categories)).append("\n");
    }
    return text.toString();
  }

  public void reloadMapping() {
    mappingRequested = false;
    requestMapping();
  }

  private void requestMapping() {
    if (mappingRequested || mappingInFlight || api == null || motionNames.isEmpty()
        || controller.state() != State.IDLE) return;
    mappingRequested = true;
    mappingInFlight = true;
    long current = engine;
    api.mapping(body -> scheduler.execute(() -> {
      if (!isCurrent(current)) return;
      mappingInFlight = false;
      if (controller.state() != State.IDLE) {
        mappingRequested = false;
        return;
      }
      applyMapping(body);
      publish();
    }), message -> scheduler.execute(() -> {
      if (!isCurrent(current)) return;
      mappingInFlight = false;
      mappingStatus = "② " + message;
      publish();
    }));
  }

  private void applyMapping(String body) {
    try {
      Set<String> available = controller.motions();
      int gifCount = motions.installServerMapping(body, available, registry);
      mappingStatus = "② 事前分類表: 適用済み / SDK " + available.size() + "動作 / GIF "
          + gifCount + "件・その他は名称等の暫定分類";
    } catch (RuntimeException ignored) {
      mappingStatus = "② 事前分類表: 不正な表のため未適用";
    }
  }

  public void refreshMotions() {
    if (robot != null) robot.refreshMotions();
  }

  public String motionSummary() {
    return registry == null ? "" : registry.json();
  }

  public static final class MotionAssignment {
    public final boolean enabled, showMp4;
    public final long durationMs, cooldownMs;
    public final String scene;

    private MotionAssignment(Motion motion) {
      enabled = motion.enabled;
      showMp4 = motion.showMp4;
      durationMs = motion.durationMs;
      cooldownMs = motion.cooldownMs;
      scene = motion.scene;
    }
  }

  public MotionAssignment assignment(Gesture gesture, String id) {
    if (registry == null) return null;
    for (Motion motion : registry.entries(gesture)) {
      if (motion.id.equals(id)) return new MotionAssignment(motion);
    }
    return null;
  }

  public boolean saveMotion(Gesture gesture, String id, String duration, String cooldown,
      boolean showMp4, boolean enabled, String scene) {
    if (controller == null || !controller.motions().contains(id)) return false;
    try {
      Motion motion = new Motion(id);
      motion.durationMs = Long.parseLong(duration);
      motion.cooldownMs = Long.parseLong(cooldown);
      motion.showMp4 = showMp4;
      motion.enabled = enabled;
      motion.scene = scene;
      registry.assign(gesture, motion);
    } catch (IllegalArgumentException ignored) {
      return false;
    }
    motions.save(registry);
    return true;
  }

  public void removeMotion(Gesture gesture, String id) {
    if (registry == null) return;
    registry.remove(gesture, id);
    motions.save(registry);
  }

  public String latencyWarning() { return latency.warning(); }

  public String latencyHistory() { return latency.historyText(); }

  public String latencyCsv() { return latency.csv(); }

  public boolean exportLatencyCsv(Uri location, String csv) {
    try {
      latency.exportCsv(getApplication(), location, csv);
      return true;
    } catch (IOException ignored) {
      showError("速度履歴のCSV保存に失敗しました。");
      return false;
    }
  }

  public void clearLatency() {
    latency.clear();
    publish();
  }

  public String traceText() { return trace.text(); }

  public void clearTrace() { trace.clear(); }
}
