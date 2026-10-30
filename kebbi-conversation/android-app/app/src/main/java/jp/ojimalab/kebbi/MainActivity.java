package jp.ojimalab.kebbi;

import static jp.ojimalab.kebbi.core.RuntimePorts.*;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.InputType;
import android.text.method.PasswordTransformationMethod;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.util.*;
import com.google.gson.*;
import jp.ojimalab.kebbi.core.*;

public final class MainActivity extends Activity {
  private final AndroidScheduler scheduler = new AndroidScheduler();
  private SharedPreferences prefs;
  private JsonTrace trace;
  private LatencyStore latency;
  private TextView latencyLatest, mappingStatus;
  private boolean mappingFetched;
  private Set<String> lastCatalog = new TreeSet<>();
  private String pendingCsv;
  private ApiClient api;
  private RobotAdapter robot;
  private ConversationController controller;
  private MotionRegistry registry;
  private LinearLayout root;
  private TextView sdkStatus, backendStatus, stateStatus, userText, replyText, selection, errorText;
  private EditText input;
  private Spinner testGesture, experiment, conversationLanguage, replyModel;
  private Button listen, asrOnly, send, tts, combined, motionButton;
  private long engine;
  private boolean active;
  private String lastContent = "";
  private ArrayAdapter<String> adminNames;
  private List<String> lastNames = new ArrayList<>();

  private int dp(int n) {
    return (int) (n * getResources().getDisplayMetrics().density);
  }

  @Override
  public void onCreate(Bundle saved) {
    super.onCreate(saved);
    prefs = getSharedPreferences("kebbi", MODE_PRIVATE);
    trace = new JsonTrace(this, prefs);
    latency = new LatencyStore(this);
    buildUi();
  }

  @Override
  protected void onStart() {
    super.onStart();
    active = true;
    startEngine();
  }

  @Override
  protected void onStop() {
    active = false;
    endEngine();
    super.onStop();
  }

  private void endEngine() {
    engine++;
    if (controller != null) controller.close();
    if (api != null) api.close();
    controller = null;
    api = null;
    robot = null;
  }

  private String loadMapping() {
    String stored = prefs.getString("mapping", null);
    if (stored != null) return stored;
    try (InputStream in = getAssets().open("gesture_mapping.json");
        ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      byte[] b = new byte[2048];
      int n;
      while ((n = in.read(b)) != -1) out.write(b, 0, n);
      return out.toString("UTF-8");
    } catch (IOException e) {
      return "{}";
    }
  }

  private void startEngine() {
    if (!active || controller != null) return;
    long current = ++engine;
    try {
      registry = MotionRegistry.parse(loadMapping());
    } catch (RuntimeException error) {
      registry = new MotionRegistry();
      errorText.setText("モーション設定が不正です。管理画面で設定し直してください。");
    }
    try {
      api =
          new ApiClient(
              prefs.getString("url", "http://10.0.2.2:8000"), prefs.getString("token", ""));
    } catch (RuntimeException error) {
      errorText.setText("API URLが不正です。設定を修正してください。");
      return;
    }
    mappingFetched = false;
    robot = RobotFactory.create(this, scheduler);
    robot.configureMock("Hello, Kebbi!", prefs.getString("mock_fault", "none"));
    controller =
        new ConversationController(
            robot,
            api,
            scheduler,
            (turn, event, fields) -> {
              if (event.equals("metrics")) {
                latency.record(turn, fields);
                if (latencyLatest != null) latencyLatest.setText(latency.history.latestText() + "\n" + latency.warning);
              }
              trace.event(turn, event, fields);
            },
            s -> {
              if (current == engine && active) render(s);
            },
            registry);
    controller.settings(prefs.getString("language", "en"), prefs.getBoolean("motion", true));
    controller.replyModel(SelectionOptions.REPLY_MODELS.get(replyModel.getSelectedItemPosition()));
    conversationLanguage.setSelection(prefs.getString("language", "en").equals("ja") ? 1 : 0);
    int condition = prefs.getInt("experiment", 0);
    controller.experiment(condition == 2 ? "direct" : "category", condition == 1 ? "expanded" : "basic");
    controller.connect();
    health();
  }

  private TextView label(LinearLayout parent, String text, int size) {
    TextView v = new TextView(this);
    v.setText(text);
    v.setTextSize(size);
    v.setPadding(0, dp(5), 0, dp(5));
    parent.addView(v);
    return v;
  }

  private EditText edit(LinearLayout parent, String hint, String value) {
    EditText e = new EditText(this);
    e.setHint(hint);
    e.setText(value);
    e.setTextSize(16);
    parent.addView(e, new LinearLayout.LayoutParams(-1, -2));
    return e;
  }

  private Button button(LinearLayout parent, String text, Runnable action) {
    Button b = new Button(this);
    b.setText(text);
    b.setAllCaps(false);
    parent.addView(b, new LinearLayout.LayoutParams(-1, -2));
    b.setOnClickListener(v -> action.run());
    return b;
  }

  private Spinner spinner(LinearLayout parent, List<String> choices) {
    Spinner s = new Spinner(this);
    ArrayAdapter<String> a =
        new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, choices);
    s.setAdapter(a);
    parent.addView(s);
    return s;
  }

  private CheckBox check(LinearLayout parent, String text, boolean value) {
    CheckBox c = new CheckBox(this);
    c.setText(text);
    c.setChecked(value);
    parent.addView(c);
    return c;
  }

  private LinearLayout panel() {
    LinearLayout p = new LinearLayout(this);
    p.setOrientation(LinearLayout.VERTICAL);
    p.setPadding(dp(18), dp(12), dp(18), dp(16));
    return p;
  }

  private ScrollView scroll(LinearLayout p) {
    ScrollView scroll = new ScrollView(this);
    scroll.addView(p);
    return scroll;
  }

  private void buildUi() {
    root = panel();
    setContentView(scroll(root));
    label(root, "Kebbi Conversation · " + (RobotFactory.REAL ? "実機モード" : "モックモード"), 24)
        .setTypeface(null, Typeface.BOLD);
    sdkStatus = label(root, "SDK: 接続待ち", 16);
    backendStatus = label(root, "バックエンド: 確認中", 16);
    stateStatus = label(root, "状態: IDLE", 18);
    errorText = label(root, "", 15);
    errorText.setTextColor(0xffa02020);
    label(root, "会話の言語（音声認識・返答・読み上げ）", 16);
    conversationLanguage = spinner(root, Arrays.asList("English（英語）", "日本語"));
    conversationLanguage.setSelection(prefs.getString("language", "en").equals("ja") ? 1 : 0);
    conversationLanguage.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
      public void onNothingSelected(AdapterView<?> p) {}
      public void onItemSelected(AdapterView<?> p, android.view.View v, int position, long id) {
        String selected = position == 1 ? "ja" : "en";
        if (selected.equals(prefs.getString("language", "en"))) return;
        prefs.edit().putString("language", selected).apply();
        if (controller != null) {
          controller.newSession();
          controller.settings(selected, prefs.getBoolean("motion", true));
        }
      }
    });
    label(root, "返答生成モデル（切替時に会話履歴をリセット）", 16);
    replyModel = spinner(root, Arrays.asList("GPT-4.1 mini（現在・軽量）", "GPT-4.1（比較用・上位）",
        "GPT-5.4 mini", "GPT-5.4", "GPT-6 Luna", "GPT-6.1 Sol"));
    replyModel.setId(1010);
    replyModel.setSelection(Math.max(0, SelectionOptions.REPLY_MODELS.indexOf(prefs.getString("reply_model", SelectionOptions.REPLY_MODELS.get(0)))));
    replyModel.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
      public void onNothingSelected(AdapterView<?> p) {}
      public void onItemSelected(AdapterView<?> p, android.view.View v, int position, long id) {
        String selected = SelectionOptions.REPLY_MODELS.get(position);
        if (selected.equals(prefs.getString("reply_model", SelectionOptions.REPLY_MODELS.get(0)))) return;
        if (controller != null) controller.replyModel(selected);
        prefs.edit().putString("reply_model", selected).apply();
      }
    });
    label(root, "返答文章だけモデルを切替。動作選択は固定モデル。5・6系は推論lowで比較します。", 14);
    label(root, "実験条件（切替時に会話履歴をリセット）", 16);
    experiment = spinner(root, Arrays.asList("② カテゴリ経由・従来7種", "② カテゴリ経由・拡張25種", "① 動作IDをLLMが直接選択"));
    label(root, "②はLLMがカテゴリを選び、その候補内の動作IDもLLMが選択します。", 14);
    experiment.setSelection(prefs.getInt("experiment", 0));
    experiment.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
      public void onNothingSelected(AdapterView<?> p) {}
      public void onItemSelected(AdapterView<?> p, android.view.View v, int position, long id) {
        if (position == prefs.getInt("experiment", 0)) return;
        prefs.edit().putInt("experiment", position).apply();
        if (controller != null) controller.experiment(position == 2 ? "direct" : "category", position == 1 ? "expanded" : "basic");
      }
    });
    button(root, "LLMに渡す動作候補を確認", () -> {
      if (controller == null) return;
      List<SelectionOptions.Candidate> candidates = experiment.getSelectedItemPosition() == 2 ? registry.candidates(controller.motions(), scheduler.now())
          : registry.categoryCandidates(controller.motions(),scheduler.now(),experiment.getSelectedItemPosition()==1);
      StringBuilder text = new StringBuilder("現在の候補: " + candidates.size() + "件 / SDK一覧 " + controller.motions().size() + "件\n①はSDK全動作から選択（クールダウン中を除く）。②はLLMがカテゴリを選び、そのカテゴリ内のIDもLLMが選択。\n");
      for (SelectionOptions.Candidate m : candidates) text.append("\n").append(m.id).append("\n").append(m.description).append("\nカテゴリ: ").append(String.join(", ",m.categories)).append("\n");
      TextView body = label(panel(), text.toString(), 16);
      new AlertDialog.Builder(this).setTitle("LLMに渡す動作候補").setView(scroll((LinearLayout)body.getParent())).setPositiveButton("閉じる", null).show();
    });
    mappingStatus = label(root, "② 事前分類表: 確認待ち", 14);
    button(root, "事前分類表を再取得", () -> { mappingFetched = false; loadPreclassifiedMapping(); });
    listen = button(root, "会話を開始（返答後も自動で聞き取り）", () -> startAsr(false));
    listen.setId(1001);
    button(
        root,
        "会話を終了 / 停止",
        () -> {
          if (controller != null) controller.stop();
        });
    input = edit(root, "手動入力 / モックASRの発話", "");
    input.setId(1002);
    send =
        button(
            root,
            "テキストで会話",
            () -> {
              if (controller != null) controller.submit(input.getText().toString());
            });
    send.setId(1003);
    userText = label(root, "認識した発話: —", 17);
    userText.setId(1004);
    replyText = label(root, "Kebbiの応答: —", 19);
    replyText.setId(1005);
    selection = label(root, "ジェスチャー: none / モーション: なし", 16);
    selection.setId(1006);
    latencyLatest = label(root, latency.history.latestText(), 16);
    latencyLatest.setId(1008);
    button(root, "返答速度・履歴 / CSV保存", this::showLatency);
    label(root, "機能別テスト", 20);
    List<String> labels = new ArrayList<>();
    for (Gesture g : Gesture.values()) labels.add(g.name());
    testGesture = spinner(root, labels);
    tts = button(root, "TTSのみ", () -> test(false));
    combined = button(root, "TTS + ジェスチャー", () -> test(true));
    asrOnly = button(root, "ASRのみ", () -> startAsr(true));
    motionButton = button(root, "モーション管理・単独再生", this::showMotions);
    button(root, "設定", this::settings);
    button(
        root,
        "接続を確認 / SDK再接続",
        () -> {
          if (controller != null && controller.state() == State.IDLE) controller.connect();
          else if (controller == null) startEngine();
          health();
        });
    button(
        root,
        "新しい会話（履歴を破棄）",
        () -> {
          if (controller != null) controller.newSession();
        });
    button(
        root,
        "JSONイベント・所要時間",
        () -> {
          TextView text = label(panel(), "", 13);
          text.setText(trace.text().isEmpty() ? "イベントはまだありません。" : trace.text());
          text.setTextIsSelectable(true);
          new AlertDialog.Builder(this)
              .setTitle("JSON Lines（直近100件）")
              .setView(scroll((LinearLayout) text.getParent()))
              .setPositiveButton("閉じる", null)
              .show();
        });
    button(
        root,
        "端末内ログを消去",
        () ->
            new AlertDialog.Builder(this)
                .setMessage("このアプリの保存ログを消去しますか？")
                .setNegativeButton("キャンセル", null)
                .setPositiveButton("消去", (d, w) -> trace.clear())
                .show());
    label(
        root,
        RobotFactory.REAL ? "実機のモーション一覧で確認したIDだけを割り当ててください。" : "mock_から始まる動作はテスト用です。実機IDではありません。",
        14);
  }

  private void render(Snapshot s) {
    sdkStatus.setText(
        "SDK: "
            + (s.connected ? "接続済み" : "接続待ち / 再接続が必要")
            + (RobotFactory.REAL ? "" : " (MockRobotAdapter)"));
    stateStatus.setText("状態: " + s.state + (s.state==State.LISTENING ? "（聞き取り中：話しかけてください）" : "") + " / TTS完了=" + s.ttsDone + " / Motion完了=" + s.motionDone
        + (s.continuous ? "\n会話継続中（終了 / 停止で聞き取りを終了）" : "")
        + (s.sentenceCount>0 ? " / 文 " + (s.sentenceIndex+1) + "/" + s.sentenceCount : ""));
    stateStatus.setId(1007);
    userText.setText("認識した発話: " + s.text);
    if (!s.speech.isEmpty() || !s.continuous) replyText.setText("Kebbiの応答: " + s.speech);
    selection.setText(
        "ジェスチャー: " + s.gesture + " / モーション: " + (s.motion.isEmpty() ? "なし" : s.motion));
    errorText.setText(s.message);
    if (controller != null && !controller.motions().isEmpty()) {
      if (!lastCatalog.equals(controller.motions())) {
        lastCatalog = new TreeSet<>(controller.motions());
        writeCatalog();
      }
      if (!mappingFetched) loadPreclassifiedMapping();
    }
    experiment.setEnabled(s.state == State.IDLE && !s.continuous);
    conversationLanguage.setEnabled(s.state == State.IDLE && !s.continuous);
    replyModel.setEnabled(s.state == State.IDLE && !s.continuous);
    boolean idle = s.connected && s.state == State.IDLE && !s.continuous;
    for (Button b : Arrays.asList(listen, asrOnly, send, tts, combined, motionButton))
      b.setEnabled(idle);
    if (!s.speech.isEmpty() && !s.turnId.equals(lastContent)) {
      lastContent = s.turnId;
      trace.content(s.turnId, s.text, s.speech);
    }
    if (adminNames != null && controller != null) {
      List<String> names = new ArrayList<>(controller.motions());
      if (!names.equals(lastNames)) {
        lastNames = names;
        adminNames.clear();
        adminNames.addAll(names);
        adminNames.notifyDataSetChanged();
      }
    }
  }

  private void writeCatalog() {
    android.util.AtomicFile file = new android.util.AtomicFile(new File(getFilesDir(), "motion-catalog.json"));
    FileOutputStream out = null;
    try {
      out = file.startWrite();
      out.write(new Gson().toJson(lastCatalog).getBytes(java.nio.charset.StandardCharsets.UTF_8));
      file.finishWrite(out);
    } catch (IOException e) { if (out != null) file.failWrite(out); }
  }

  private void loadPreclassifiedMapping() {
    if (api == null || controller == null || controller.motions().isEmpty()) return;
    mappingFetched = true;
    long current = engine;
    api.mapping(body -> scheduler.execute(() -> {
      if (current != engine || !active || controller == null) return;
      if (controller.state() != State.IDLE) { mappingFetched = false; return; }
      try {
        JsonObject response = JsonParser.parseString(body).getAsJsonObject();
        MotionRegistry replacement = MotionRegistry.parse(response.get("mapping").toString());
        int count = 0;
        for (Gesture g : Gesture.values()) for (Motion m : replacement.entries(g)) {
          if (!controller.motions().contains(m.id)) throw new IllegalArgumentException();
          count++;
        }
        if (count == 0) throw new IllegalArgumentException();
        registry.replaceMappings(replacement);
        prefs.edit().putString("mapping", registry.json()).apply();
        mappingStatus.setText("② 事前分類表: 適用済み / SDK " + controller.motions().size() + "動作 / GIF " + (response.has("gif_count") ? response.get("gif_count").getAsInt() : 0) + "件・その他は名称等の暫定分類");
      } catch (RuntimeException e) { mappingStatus.setText("② 事前分類表: 不正な表のため未適用"); }
    }), message -> scheduler.execute(() -> {
      if (current == engine && active) mappingStatus.setText("② " + message);
    }));
  }

  private void showLatency() {
    LinearLayout p = panel();
    label(p, "時間は秒表示。返答開始は、音声では認識結果確定、手動入力では送信からTTS開始通知まで。LLM待ちは通信を含みます。", 15);
    label(p, "操作→発声はASR待ちを含みます。SDK通知による計測で、音響的な開始の実測ではありません。未計測は—。", 14);
    label(p, "本文・APIキーを含めず直近200件を自動保存。" + latency.warning, 14);
    button(p, "CSVに保存", () -> {
      pendingCsv = "\uFEFF" + latency.history.csv();
      Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
      intent.addCategory(Intent.CATEGORY_OPENABLE);
      intent.setType("text/csv");
      intent.putExtra(Intent.EXTRA_TITLE, "kebbi-latency-" + System.currentTimeMillis() + ".csv");
      try { startActivityForResult(intent, 11); }
      catch (ActivityNotFoundException e) { pendingCsv = null; errorText.setText("保存先を選ぶアプリがありません。ADBで履歴JSONを取得できます。"); }
    });
    TextView history = label(p, latency.history.historyText(), 15);
    history.setTextIsSelectable(true);
    button(p, "速度履歴を消去", () -> new AlertDialog.Builder(this)
      .setMessage("保存した速度履歴を消去しますか？")
      .setNegativeButton("キャンセル", null)
      .setPositiveButton("消去", (d, w) -> {
        latency.clear(); latencyLatest.setText(latency.history.latestText());
        history.setText(latency.history.historyText());
      }).show());
    new AlertDialog.Builder(this).setTitle("返答速度と履歴").setView(scroll(p)).setPositiveButton("閉じる", null).show();
  }

  @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
    super.onActivityResult(requestCode, resultCode, data);
    if (requestCode != 11) return;
    String csv = pendingCsv; pendingCsv = null;
    if (resultCode != RESULT_OK || data == null || data.getData() == null || csv == null) return;
    try (OutputStream out = getContentResolver().openOutputStream(data.getData())) {
      if (out == null) throw new IOException();
      out.write(csv.getBytes(java.nio.charset.StandardCharsets.UTF_8));
      Toast.makeText(this, "速度履歴をCSVに保存しました", Toast.LENGTH_LONG).show();
    } catch (IOException e) { errorText.setText("速度履歴のCSV保存に失敗しました。"); }
  }

  private void health() {
    if (api == null) return;
    long current = engine;
    backendStatus.setText("バックエンド: 確認中");
    api.health(
        status ->
            scheduler.execute(
                () -> {
                  if (current == engine && active) backendStatus.setText("バックエンド: " + status);
                }));
  }

  private void startAsr(boolean only) {
    if (controller == null) return;
    if (RobotFactory.REAL
        && checkSelfPermission(Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) {
      pendingAsrOnly = only;
      requestPermissions(new String[] {Manifest.permission.RECORD_AUDIO}, 7);
      return;
    }
    robot.configureMock(
        input.getText().toString().isEmpty() ? "Hello, Kebbi!" : input.getText().toString(),
        prefs.getString("mock_fault", "none"));
    if (only) controller.listen(true); else controller.startConversation();
  }

  private boolean pendingAsrOnly;

  @Override
  public void onRequestPermissionsResult(int request, String[] permissions, int[] grants) {
    super.onRequestPermissionsResult(request, permissions, grants);
    if (request == 7 && grants.length > 0 && grants[0] == PackageManager.PERMISSION_GRANTED)
      startAsr(pendingAsrOnly);
    else errorText.setText("マイク権限が必要です。");
  }

  private void test(boolean both) {
    if (controller == null) return;
    robot.configureMock("Hello, Kebbi!", prefs.getString("mock_fault", "none"));
    controller.testSpeech(
        input.getText().toString(), Gesture.safe(testGesture.getSelectedItem().toString()), both);
  }

  private void settings() {
    if (controller != null) controller.stop();
    LinearLayout p = panel();
    label(p, "接続と言語", 19);
    EditText url = edit(p, "バックエンドURL", prefs.getString("url", "http://10.0.2.2:8000"));
    EditText token = edit(p, "バックエンドの共有トークン（任意）", prefs.getString("token", ""));
    token.setTransformationMethod(PasswordTransformationMethod.getInstance());
    label(p, "LLMのAPIキーはこの画面に入力しません。サーバーの環境変数で管理します。", 14);
    Spinner lang = spinner(p, Arrays.asList("English（英語）", "日本語"));
    lang.setSelection(prefs.getString("language", "en").equals("ja") ? 1 : 0);
    CheckBox motion = check(p, "ジェスチャーモーションを有効化", prefs.getBoolean("motion", true));
    label(p, "音声認識モード: ボタン開始（MVP）", 15);
    CheckBox log = check(p, "メタデータ・時間のJSONログ", prefs.getBoolean("log", true));
    CheckBox persist = check(p, "JSONLをアプリ専用領域へ保存", prefs.getBoolean("persist", false));
    CheckBox content = check(p, "会話本文も記録する（明示的に有効にした場合のみ）", prefs.getBoolean("content", false));
    label(p, "モックの障害シミュレーション", 16);
    List<String> faults =
        Arrays.asList(
            "none",
            "asr_error",
            "asr_timeout",
            "tts_error",
            "tts_timeout",
            "motion_error",
            "motion_timeout");
    Spinner fault = spinner(p, faults);
    fault.setSelection(Math.max(0, faults.indexOf(prefs.getString("mock_fault", "none"))));
    fault.setEnabled(!RobotFactory.REAL);
    AlertDialog d =
        new AlertDialog.Builder(this)
            .setTitle("設定")
            .setView(scroll(p))
            .setNegativeButton("キャンセル", null)
            .setPositiveButton("保存", null)
            .create();
    d.setOnShowListener(
        ignored ->
            d.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(
                    v -> {
                      String newUrl = url.getText().toString().trim();
                      try {
                        new ApiClient(newUrl, "").close();
                      } catch (RuntimeException e) {
                        url.setError("http(s)のURLを指定してください");
                        return;
                      }
                      endEngine();
                      prefs
                          .edit()
                          .putString("url", newUrl)
                          .putString("token", token.getText().toString())
                          .putString("language", lang.getSelectedItemPosition() == 1 ? "ja" : "en")
                          .putBoolean("motion", motion.isChecked())
                          .putBoolean("log", log.isChecked())
                          .putBoolean("persist", persist.isChecked())
                          .putBoolean("content", content.isChecked())
                          .putString("mock_fault", fault.getSelectedItem().toString())
                          .apply();
                      startEngine();
                      d.dismiss();
                    }));
    d.show();
  }

  private void showMotions() {
    if (controller == null) return;
    LinearLayout p = panel();
    label(p, "一覧はSDKから取得します。①は全一覧、②は事前分類表・この対応表を使います。", 15);
    lastNames = new ArrayList<>(controller.motions());
    Spinner ids = new Spinner(this);
    adminNames =
        new ArrayAdapter<>(
            this, android.R.layout.simple_spinner_dropdown_item, new ArrayList<>(lastNames));
    ids.setAdapter(adminNames);
    p.addView(ids);
    List<String> categories = new ArrayList<>();
    for (Gesture g : Gesture.values()) if (g != Gesture.none) categories.add(g.name());
    Spinner category = spinner(p, categories);
    CheckBox enabled = check(p, "この割り当てを有効化", true), mp4 = check(p, "モーションのMP4表示", false);
    EditText duration = edit(p, "動作時間 ms（参考メタデータ）", "4000"),
        cooldown = edit(p, "クールダウン ms", "5000"),
        scene = edit(p, "動作の説明・推奨場面（LLMに渡す、200字以内）", "");
    duration.setInputType(InputType.TYPE_CLASS_NUMBER);
    cooldown.setInputType(InputType.TYPE_CLASS_NUMBER);
    TextView summary = label(p, "", 13);
    summary.setText(registry.json());
    button(p, "一覧を再取得", () -> robot.refreshMotions());
    button(
        p,
        "選択した動作を単独再生",
        () -> {
          if (ids.getSelectedItem() != null) {
            robot.configureMock("", prefs.getString("mock_fault", "none"));
            controller.testMotion(ids.getSelectedItem().toString());
          }
        });
    button(
        p,
        "この割り当てを読み込む",
        () -> {
          if (ids.getSelectedItem() == null) return;
          String id = ids.getSelectedItem().toString();
          for (Motion m : registry.entries(Gesture.safe(category.getSelectedItem().toString())))
            if (m.id.equals(id)) {
              enabled.setChecked(m.enabled);
              mp4.setChecked(m.showMp4);
              duration.setText(Long.toString(m.durationMs));
              cooldown.setText(Long.toString(m.cooldownMs));
              scene.setText(m.scene);
            }
        });
    button(
        p,
        "割り当てを保存 / 更新",
        () -> {
          if (ids.getSelectedItem() == null) return;
          try {
            Motion m = new Motion(ids.getSelectedItem().toString());
            m.durationMs = Long.parseLong(duration.getText().toString());
            m.cooldownMs = Long.parseLong(cooldown.getText().toString());
            m.showMp4 = mp4.isChecked();
            m.enabled = enabled.isChecked();
            m.scene = scene.getText().toString();
            registry.assign(Gesture.safe(category.getSelectedItem().toString()), m);
            prefs.edit().putString("mapping", registry.json()).apply();
            summary.setText(registry.json());
          } catch (RuntimeException e) {
            cooldown.setError("時間設定の範囲を確認してください");
          }
        });
    button(
        p,
        "選択カテゴリから割り当てを削除",
        () -> {
          if (ids.getSelectedItem() != null) {
            registry.remove(
                Gesture.safe(category.getSelectedItem().toString()),
                ids.getSelectedItem().toString());
            prefs.edit().putString("mapping", registry.json()).apply();
            summary.setText(registry.json());
          }
        });
    AlertDialog d =
        new AlertDialog.Builder(this)
            .setTitle("モーション管理")
            .setView(scroll(p))
            .setPositiveButton("閉じる", null)
            .create();
    d.setOnDismissListener(ignored -> adminNames = null);
    d.show();
  }
}
