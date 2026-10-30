package jp.ojimalab.kebbi;

import android.app.Activity;
import android.os.*;
import android.view.WindowManager;
import android.widget.*;
import com.nuwarobotics.service.IClientId;
import com.nuwarobotics.service.agent.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;
import org.json.*;

/** USB-shell-only diagnostic in realDebug. No backend, ASR or motion API calls. */
public final class TtsBenchmarkActivity extends Activity {
  private static final int REPEATS = 10, GAP_MS = 750, TIMEOUT_MS = 45000;
  private final Handler main = new Handler(Looper.getMainLooper());
  private final List<Trial> trials = new ArrayList<>();
  private NuwaRobotAPI api;
  private TextView status;
  private FileOutputStream output;
  private volatile Trial active;
  private boolean ready, running, finished;
  private int next;
  private String runId;

  private static final class Trial {
    final String id, text;
    final int repeat;
    final boolean warmup;
    volatile long requestNs, returnNs;
    final AtomicLong startNs = new AtomicLong(), completeNs = new AtomicLong();
    volatile String speakType = "";
    Trial(JSONObject item, int repeat, boolean warmup) throws JSONException {
      id=item.getString("id"); text=item.getString("text"); this.repeat=repeat; this.warmup=warmup;
    }
  }

  @Override public void onCreate(Bundle saved) {
    super.onCreate(saved);
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    LinearLayout panel=new LinearLayout(this); panel.setOrientation(LinearLayout.VERTICAL);
    panel.setPadding(24,24,24,24);
    status=new TextView(this); status.setTextSize(20); panel.addView(status);
    Button stop=new Button(this); stop.setText("計測を中止して会話画面へ戻る");
    stop.setOnClickListener(v -> finish()); panel.addView(stop); setContentView(panel);
    try {
      runId=getIntent().getStringExtra("run_id");
      if (runId==null || !runId.matches("[A-Za-z0-9_-]{1,80}"))
        throw new IllegalArgumentException("valid run_id required");
      File directory=new File(getFilesDir(),"tts-benchmark");
      if (!directory.isDirectory() && !directory.mkdirs()) throw new IOException("mkdir");
      File file=new File(directory,runId+".jsonl");
      if (!file.createNewFile()) throw new IOException("run_id already exists");
      output=new FileOutputStream(file);
      JSONArray cases;
      try (InputStream in=getAssets().open("tts-benchmark-cases.json");
          ByteArrayOutputStream bytes=new ByteArrayOutputStream()) {
        byte[] buffer=new byte[2048]; int n;
        while ((n=in.read(buffer))!=-1) bytes.write(buffer,0,n);
        cases=new JSONArray(new String(bytes.toByteArray(),StandardCharsets.UTF_8));
      }
      for (int c=0;c<cases.length();c++) trials.add(new Trial(cases.getJSONObject(c),0,true));
      // Rotate the text order each block: every length occupies every position.
      for (int r=1;r<=REPEATS;r++)
        for (int c=0;c<cases.length();c++)
          trials.add(new Trial(cases.getJSONObject((c+r-1)%cases.length()),r,false));
      JSONObject meta=new JSONObject().put("event","protocol").put("run_id",runId)
          .put("schema_version",1).put("wall_time_ms",System.currentTimeMillis())
          .put("clock","SystemClock.elapsedRealtimeNanos")
          .put("language","ja_JP").put("cases",cases).put("repeats",REPEATS)
          .put("warmups",cases.length()).put("gap_ms",GAP_MS).put("timeout_ms",TIMEOUT_MS)
          .put("app_version",getPackageManager().getPackageInfo(getPackageName(),0).versionName)
          .put("model",Build.MODEL).put("android_release",Build.VERSION.RELEASE)
          .put("fingerprint",Build.FINGERPRINT);
      write(meta);
      status.setText("NUWA SDK接続待ち。TTSのみ33回を自動計測します。");
      api=new NuwaRobotAPI(this,new IClientId(getPackageName()));
      api.registerRobotEventListener(new RobotEventCallback() {
        @Override public void onWikiServiceStart() { main.post(() -> serviceReady()); }
        @Override public void onWikiServiceRecovery() { main.post(() -> serviceLost("sdk_recovery")); }
        @Override public void onWikiServiceStop() { main.post(() -> serviceLost("sdk_stopped")); }
        @Override public void onWikiServiceCrash() { main.post(() -> serviceLost("sdk_crashed")); }
        @Override public void onWikiServiceError(int code) { main.post(() -> serviceLost("sdk_error_"+code)); }
      });
      main.postDelayed(() -> { if (!ready && !finished) end("sdk_connect_timeout"); },15000);
    } catch (Exception error) { end("setup_error:"+error.getClass().getSimpleName()); }
  }

  private void serviceReady() {
    if (ready || finished) return;
    ready=true; running=true;
    // Give the service binding time to settle; this interval is outside every measurement.
    main.postDelayed(() -> nextTrial(),1000);
  }

  private void nextTrial() {
    if (!running || finished) return;
    if (next==trials.size()) { end("complete"); return; }
    Trial t=trials.get(next++); active=t;
    status.setText("TTSのみ計測中 "+next+" / "+trials.size()+"\n"
        +(t.warmup?"ウォームアップ":t.id+" / "+t.repeat)+"\n"+t.text);
    try {
      api.registerVoiceEventListener(new VoiceEventCallback() {
        @Override public void onSpeakState(VoiceEventListener.SpeakType type,
            VoiceEventListener.SpeakState state) {
          // Capture at callback entry, before posting to the UI thread or writing a log.
          long received=SystemClock.elapsedRealtimeNanos();
          if (active==t && t.requestNs!=0 && state==VoiceEventListener.SpeakState.START
              && t.startNs.compareAndSet(0,received)) t.speakType=String.valueOf(type);
        }
        @Override public void onTTSComplete(boolean error) {
          long received=SystemClock.elapsedRealtimeNanos();
          if (active==t && t.requestNs!=0 && t.completeNs.compareAndSet(0,received))
            main.post(() -> finishTrial(t,error?"tts_error":"ok"));
        }
      });
      // Nothing (including logging) between this timestamp and the SDK invocation.
      t.requestNs=SystemClock.elapsedRealtimeNanos();
      api.startTTS(t.text,NuwaRobotAPI.JAPAN);
      t.returnNs=SystemClock.elapsedRealtimeNanos();
      main.postDelayed(() -> { if (active==t) finishTrial(t,"timeout"); },TIMEOUT_MS);
    } catch (RuntimeException error) { finishTrial(t,"tts_call_error"); }
  }

  private void finishTrial(Trial t,String outcome) {
    if (active!=t) return;
    active=null;
    long start=t.startNs.get(), complete=t.completeNs.get();
    if (outcome.equals("ok") && (start<t.requestNs || complete<start || t.returnNs<t.requestNs))
      outcome="missing_or_invalid_timestamp";
    try {
      JSONObject row=new JSONObject().put("event","trial").put("run_id",runId)
          .put("case_id",t.id).put("text",t.text).put("characters",t.text.codePointCount(0,t.text.length()))
          .put("repeat",t.repeat).put("warmup",t.warmup).put("status",outcome)
          .put("request_ns",t.requestNs).put("call_return_ns",t.returnNs)
          .put("start_callback_ns",start).put("complete_callback_ns",complete)
          .put("speak_type",t.speakType);
      write(row);
    } catch (Exception error) { end("write_error"); return; }
    // Abort after a failure: late callbacks carry no SDK request ID and could taint the next trial.
    if (!outcome.equals("ok")) { end(outcome); return; }
    main.postDelayed(() -> nextTrial(),GAP_MS);
  }

  private void serviceLost(String reason) {
    if (finished) return;
    if (active!=null) finishTrial(active,reason); else end(reason);
  }

  private void write(JSONObject row) throws IOException {
    output.write((row.toString()+"\n").getBytes(StandardCharsets.UTF_8));
    output.flush();
  }

  private void end(String reason) {
    if (finished) return;
    finished=true; running=false; active=null;
    main.removeCallbacksAndMessages(null);
    try { if (output!=null) write(new JSONObject().put("event","finished")
        .put("run_id",runId).put("status",reason).put("trials_written",next)); }
    catch (Exception ignored) {}
    try { if (output!=null) output.close(); } catch (IOException ignored) {}
    output=null;
    if (api!=null) {
      try { api.stopTTS(); } catch (RuntimeException ignored) {}
      try { api.release(); } catch (RuntimeException ignored) {}
      api=null;
    }
    status.setText(reason.equals("complete")?"TTS計測完了。結果をKebbi内に保存しました。"
        :"計測終了: "+reason+"\n完了した試行は保存されています。");
  }

  @Override protected void onStop() {
    if (!finished) {
      if (active!=null) finishTrial(active,"interrupted"); else end("interrupted");
    }
    super.onStop();
  }
}
