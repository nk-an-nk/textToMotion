package jp.ojimalab.kebbi.ui.view;

import android.Manifest;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.InputType;
import android.text.method.PasswordTransformationMethod;
import android.widget.*;
import androidx.activity.ComponentActivity;
import androidx.lifecycle.ViewModelProvider;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import jp.ojimalab.kebbi.core.Gesture;
import jp.ojimalab.kebbi.core.RuntimePorts.State;
import jp.ojimalab.kebbi.data.SettingsStore.ConnectionSettings;
import jp.ojimalab.kebbi.ui.viewmodel.ConversationUiState;
import jp.ojimalab.kebbi.ui.viewmodel.ConversationViewModel;
import jp.ojimalab.kebbi.ui.viewmodel.ConversationViewModel.MotionAssignment;

public final class ConversationActivity extends ComponentActivity {
  private ConversationViewModel model;
  private LinearLayout root;
  private TextView sdkStatus, backendStatus, stateStatus, userText, replyText, selection, errorText;
  private TextView latencyLatest, mappingStatus;
  private EditText input;
  private Spinner testGesture, experiment, conversationLanguage, replyModel;
  private Button listen, asrOnly, send, tts, combined, motionButton;
  private ArrayAdapter<String> adminNames;
  private List<String> lastNames = new ArrayList<>();
  private String pendingCsv;
  private boolean pendingAsrOnly;

  private int dp(int n) {
    return (int) (n * getResources().getDisplayMetrics().density);
  }

  @Override
  public void onCreate(Bundle saved) {
    super.onCreate(saved);
    model = new ViewModelProvider(this).get(ConversationViewModel.class);
    buildUi();
    model.screen().observe(this, this::render);
  }

  @Override
  protected void onStart() {
    super.onStart();
    model.onStart();
  }

  @Override
  protected void onStop() {
    model.onStop();
    super.onStop();
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
    ConversationUiState initial = model.screen().getValue();
    root = panel();
    setContentView(scroll(root));
    label(root, "Kebbi Conversation · " + (model.isRealDevice() ? "実機モード" : "モックモード"), 24)
        .setTypeface(null, Typeface.BOLD);
    sdkStatus = label(root, "SDK: 接続待ち", 16);
    backendStatus = label(root, "バックエンド: 確認中", 16);
    stateStatus = label(root, "状態: IDLE", 18);
    stateStatus.setId(1007);
    errorText = label(root, "", 15);
    errorText.setTextColor(0xffa02020);
    label(root, "会話の言語（音声認識・返答・読み上げ）", 16);
    conversationLanguage = spinner(root, Arrays.asList("English（英語）", "日本語"));
    bindSelection(conversationLanguage, initial.languageIndex, model::selectLanguage);
    label(root, "返答生成モデル（切替時に会話履歴をリセット）", 16);
    replyModel = spinner(root, Arrays.asList("GPT-4.1 mini（現在・軽量）", "GPT-4.1（比較用・上位）",
        "GPT-5.4 mini", "GPT-5.4", "GPT-6 Luna", "GPT-6.1 Sol"));
    replyModel.setId(1010);
    bindSelection(replyModel, initial.replyModelIndex, model::selectReplyModel);
    label(root, "返答文章だけモデルを切替。動作選択は固定モデル。5・6系は推論lowで比較します。", 14);
    label(root, "実験条件（切替時に会話履歴をリセット）", 16);
    experiment = spinner(root, Arrays.asList("② カテゴリ経由・従来7種", "② カテゴリ経由・拡張25種", "① 動作IDをLLMが直接選択"));
    label(root, "②はLLMがカテゴリを選び、その候補内の動作IDもLLMが選択します。", 14);
    bindSelection(experiment, initial.experimentIndex, model::selectExperiment);
    button(root, "LLMに渡す動作候補を確認", () -> {
      String summary = model.candidateSummary();
      if (summary.isEmpty()) return;
      LinearLayout dialog = panel();
      label(dialog, summary, 16);
      new AlertDialog.Builder(this).setTitle("LLMに渡す動作候補").setView(scroll(dialog))
          .setPositiveButton("閉じる", null).show();
    });
    mappingStatus = label(root, "② 事前分類表: 確認待ち", 14);
    button(root, "事前分類表を再取得", model::reloadMapping);
    listen = button(root, "会話を開始（返答後も自動で聞き取り）", () -> startAsr(false));
    listen.setId(1001);
    button(root, "会話を終了 / 停止", model::stop);
    input = edit(root, "手動入力 / モックASRの発話", "");
    input.setId(1002);
    send = button(root, "テキストで会話", () -> model.submit(input.getText().toString()));
    send.setId(1003);
    userText = label(root, "認識した発話: —", 17);
    userText.setId(1004);
    replyText = label(root, "Kebbiの応答: —", 19);
    replyText.setId(1005);
    selection = label(root, "ジェスチャー: none / モーション: なし", 16);
    selection.setId(1006);
    latencyLatest = label(root, initial.latestLatency, 16);
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
    button(root, "接続を確認 / SDK再接続", model::reconnect);
    button(root, "新しい会話（履歴を破棄）", model::newSession);
    button(
        root,
        "JSONイベント・所要時間",
        () -> {
          TextView text = label(panel(), "", 13);
          String events = model.traceText();
          text.setText(events.isEmpty() ? "イベントはまだありません。" : events);
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
                .setPositiveButton("消去", (d, w) -> model.clearTrace())
                .show());
    label(
        root,
        model.isRealDevice() ? "実機のモーション一覧で確認したIDだけを割り当ててください。" : "mock_から始まる動作はテスト用です。実機IDではありません。",
        14);
  }

  private void bindSelection(Spinner spinner, int initial, java.util.function.IntConsumer onSelect) {
    spinner.setSaveEnabled(false);
    spinner.setSelection(initial);
    spinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
      @Override public void onNothingSelected(AdapterView<?> parent) {}

      @Override
      public void onItemSelected(AdapterView<?> parent, android.view.View view, int position, long id) {
        onSelect.accept(position);
      }
    });
  }

  private void showSelection(Spinner spinner, int selection) {
    if (spinner.getSelectedItemPosition() != selection) spinner.setSelection(selection);
  }

  private void render(ConversationUiState state) {
    sdkStatus.setText("SDK: " + (state.connected ? "接続済み" : "接続待ち / 再接続が必要")
        + (model.isRealDevice() ? "" : " (MockRobotAdapter)"));
    backendStatus.setText("バックエンド: " + state.backendStatus);
    mappingStatus.setText(state.mappingStatus);
    stateStatus.setText("状態: " + state.turnState
        + (state.turnState == State.LISTENING ? "（聞き取り中：話しかけてください）" : "")
        + " / TTS完了=" + state.ttsDone + " / Motion完了=" + state.motionDone
        + (state.continuous ? "\n会話継続中（終了 / 停止で聞き取りを終了）" : "")
        + (state.sentenceCount > 0 ? " / 文 " + (state.sentenceIndex + 1) + "/" + state.sentenceCount : ""));
    userText.setText("認識した発話: " + state.input);
    replyText.setText("Kebbiの応答: " + state.reply);
    selection.setText("ジェスチャー: " + state.gesture + " / モーション: "
        + (state.motion.isEmpty() ? "なし" : state.motion));
    errorText.setText(state.error);
    latencyLatest.setText(state.latestLatency);
    showSelection(experiment, state.experimentIndex);
    showSelection(conversationLanguage, state.languageIndex);
    showSelection(replyModel, state.replyModelIndex);
    for (Spinner spinner : Arrays.asList(experiment, conversationLanguage, replyModel)) {
      spinner.setEnabled(state.canEditConversation);
    }
    for (Button button : Arrays.asList(listen, asrOnly, send, tts, combined, motionButton)) {
      button.setEnabled(state.canStartTurn);
    }
    if (adminNames != null && !state.motionNames.equals(lastNames)) {
      lastNames = state.motionNames;
      adminNames.setNotifyOnChange(false);
      adminNames.clear();
      adminNames.addAll(lastNames);
      adminNames.notifyDataSetChanged();
    }
  }

  private void showLatency() {
    LinearLayout p = panel();
    label(p, "時間は秒表示。返答開始は、音声では認識結果確定、手動入力では送信からTTS開始通知まで。LLM待ちは通信を含みます。", 15);
    label(p, "操作→発声はASR待ちを含みます。SDK通知による計測で、音響的な開始の実測ではありません。未計測は—。", 14);
    label(p, "本文・APIキーを含めず直近200件を自動保存。" + model.latencyWarning(), 14);
    button(p, "CSVに保存", () -> {
      pendingCsv = model.latencyCsv();
      Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
      intent.addCategory(Intent.CATEGORY_OPENABLE);
      intent.setType("text/csv");
      intent.putExtra(Intent.EXTRA_TITLE, "kebbi-latency-" + System.currentTimeMillis() + ".csv");
      try { startActivityForResult(intent, 11); }
      catch (ActivityNotFoundException e) { pendingCsv = null; model.showError("保存先を選ぶアプリがありません。ADBで履歴JSONを取得できます。"); }
    });
    TextView history = label(p, model.latencyHistory(), 15);
    history.setTextIsSelectable(true);
    button(p, "速度履歴を消去", () -> new AlertDialog.Builder(this)
      .setMessage("保存した速度履歴を消去しますか？")
      .setNegativeButton("キャンセル", null)
      .setPositiveButton("消去", (d, w) -> {
        model.clearLatency();
        history.setText(model.latencyHistory());
      }).show());
    new AlertDialog.Builder(this).setTitle("返答速度と履歴").setView(scroll(p)).setPositiveButton("閉じる", null).show();
  }

  @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
    super.onActivityResult(requestCode, resultCode, data);
    if (requestCode != 11) return;
    String csv = pendingCsv; pendingCsv = null;
    if (resultCode != RESULT_OK || data == null || data.getData() == null || csv == null) return;
    if (model.exportLatencyCsv(data.getData(), csv)) {
      Toast.makeText(this, "速度履歴をCSVに保存しました", Toast.LENGTH_LONG).show();
    }
  }

  private void startAsr(boolean only) {
    if (model.isRealDevice()
        && checkSelfPermission(Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) {
      pendingAsrOnly = only;
      requestPermissions(new String[] {Manifest.permission.RECORD_AUDIO}, 7);
      return;
    }
    model.startListening(input.getText().toString(), only);
  }

  @Override
  public void onRequestPermissionsResult(int request, String[] permissions, int[] grants) {
    super.onRequestPermissionsResult(request, permissions, grants);
    if (request != 7) return;
    if (grants.length > 0 && grants[0] == PackageManager.PERMISSION_GRANTED) startAsr(pendingAsrOnly);
    else model.showError("マイク権限が必要です。");
  }

  private void test(boolean both) {
    model.testSpeech(input.getText().toString(), Gesture.safe(testGesture.getSelectedItem().toString()), both);
  }

  private void settings() {
    model.stop();
    ConnectionSettings config = model.connectionSettings();
    LinearLayout p = panel();
    label(p, "接続と言語", 19);
    EditText url = edit(p, "バックエンドURL", config.url);
    EditText token = edit(p, "バックエンドの共有トークン（任意）", config.token);
    token.setTransformationMethod(PasswordTransformationMethod.getInstance());
    label(p, "LLMのAPIキーはこの画面に入力しません。サーバーの環境変数で管理します。", 14);
    Spinner lang = spinner(p, Arrays.asList("English（英語）", "日本語"));
    lang.setSelection(config.language.equals("ja") ? 1 : 0);
    CheckBox motion = check(p, "ジェスチャーモーションを有効化", config.motion);
    label(p, "音声認識モード: ボタン開始（MVP）", 15);
    CheckBox log = check(p, "メタデータ・時間のJSONログ", config.log);
    CheckBox persist = check(p, "JSONLをアプリ専用領域へ保存", config.persist);
    CheckBox content = check(p, "会話本文も記録する（明示的に有効にした場合のみ）", config.content);
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
    fault.setSelection(Math.max(0, faults.indexOf(config.mockFault)));
    fault.setEnabled(!model.isRealDevice());
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
                      ConnectionSettings selected = new ConnectionSettings(
                          url.getText().toString().trim(), token.getText().toString(),
                          lang.getSelectedItemPosition() == 1 ? "ja" : "en", motion.isChecked(),
                          log.isChecked(), persist.isChecked(), content.isChecked(),
                          fault.getSelectedItem().toString());
                      if (!model.saveSettings(selected)) {
                        url.setError("http(s)のURLを指定してください");
                        return;
                      }
                      d.dismiss();
                    }));
    d.show();
  }

  private void showMotions() {
    ConversationUiState state = model.screen().getValue();
    if (!state.canStartTurn) return;
    LinearLayout p = panel();
    label(p, "一覧はSDKから取得します。①は全一覧、②は事前分類表・この対応表を使います。", 15);
    lastNames = state.motionNames;
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
    summary.setText(model.motionSummary());
    button(p, "一覧を再取得", model::refreshMotions);
    button(
        p,
        "選択した動作を単独再生",
        () -> {
          if (ids.getSelectedItem() != null) model.testMotion(ids.getSelectedItem().toString());
        });
    button(
        p,
        "この割り当てを読み込む",
        () -> {
          if (ids.getSelectedItem() == null) return;
          MotionAssignment assignment = model.assignment(
              Gesture.safe(category.getSelectedItem().toString()), ids.getSelectedItem().toString());
          if (assignment == null) return;
          enabled.setChecked(assignment.enabled);
          mp4.setChecked(assignment.showMp4);
          duration.setText(Long.toString(assignment.durationMs));
          cooldown.setText(Long.toString(assignment.cooldownMs));
          scene.setText(assignment.scene);
        });
    button(
        p,
        "割り当てを保存 / 更新",
        () -> {
          if (ids.getSelectedItem() == null) return;
          if (model.saveMotion(Gesture.safe(category.getSelectedItem().toString()),
              ids.getSelectedItem().toString(), duration.getText().toString(),
              cooldown.getText().toString(), mp4.isChecked(), enabled.isChecked(),
              scene.getText().toString())) {
            summary.setText(model.motionSummary());
          } else {
            cooldown.setError("時間設定の範囲を確認してください");
          }
        });
    button(
        p,
        "選択カテゴリから割り当てを削除",
        () -> {
          if (ids.getSelectedItem() != null) {
            model.removeMotion(Gesture.safe(category.getSelectedItem().toString()),
                ids.getSelectedItem().toString());
            summary.setText(model.motionSummary());
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
