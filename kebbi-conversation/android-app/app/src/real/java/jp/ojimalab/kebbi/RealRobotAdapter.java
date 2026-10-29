package jp.ojimalab.kebbi;

import android.content.Context;
import android.os.*;
import com.nuwarobotics.service.IClientId;
import com.nuwarobotics.service.agent.*;
import java.util.*;
import jp.ojimalab.kebbi.core.*;

/** The only source set importing NUWA classes. No wheel or direct joint APIs are used. */
public final class RealRobotAdapter implements RobotAdapter {
  private final Context context;
  private final Handler main = new Handler(Looper.getMainLooper());
  private NuwaRobotAPI api;
  private Events events;
  private long epoch;
  private volatile long turn;
  private volatile String playing = "";
  private boolean ready, closed;
  private long voiceGeneration;
  private PreparedSentence prepared;

  private static final class PreparedSentence {
    final long token, source;
    final Motion motion;
    final String text, language;
    PreparedSentence(long token,long source,Motion motion,String text,String language) {
      this.token=token;this.source=source;this.motion=motion;this.text=text;this.language=language;
    }
  }

  public RealRobotAdapter(Context context) {
    this.context = context;
  }

  private void post(long source, Runnable action) {
    main.post(
        () -> {
          if (!closed && source == epoch && events != null) action.run();
        });
  }

  public void connect(Events events) {
    this.events = events;
    closed = false;
    reset();
  }

  private void reset() {
    prepared=null;voiceGeneration++;
    long source = ++epoch;
    ready = false;
    turn = -1;
    playing = "";
    NuwaRobotAPI old = api;
    api = null;
    if (old != null)
      try {
        old.release();
      } catch (RuntimeException ignored) {
      }
    if (events != null) events.connected(false);
    if (closed) return;
    try {
      api = new NuwaRobotAPI(context, new IClientId(context.getPackageName()));
      api.registerRobotEventListener(
          new RobotEventCallback() {
            @Override
            public void onWikiServiceStart() {
              post(source, () -> serviceReady(source));
            }

            @Override
            public void onWikiServiceRecovery() {
              post(source, () -> serviceReady(source));
            }

            @Override
            public void onWikiServiceStop() {
              post(
                  source,
                  () -> {
                    ready = false;
                    events.connected(false);
                  });
            }

            @Override
            public void onWikiServiceCrash() {
              post(
                  source,
                  () -> {
                    ready = false;
                    events.connected(false);
                  });
            }

            @Override
            public void onWikiServiceError(int code) {
              post(
                  source,
                  () -> {
                    ready = false;
                    events.connected(false);
                  });
            }

            @Override
            public void onPrepareMotion(boolean isError, String name, float duration) {
              post(source,()-> {
                PreparedSentence item=prepared;
                if (item==null || item.source!=source || !item.motion.id.equals(name)) return;
                prepared=null;
                android.util.Log.i("KebbiSdk","sentence_motion_prepared:"+name);
                boolean started=false;
                try { started=api.motionPlay(); } catch (RuntimeException ignored) {}
                if (!started) events.motionDone(item.token,name,"motion_prepare_error");
                speakPrepared(item);
              });
            }

            @Override
            public void onStartOfMotionPlay(String name) {
              long token = turn;
              post(
                  source,
                  () -> {
                    if (name.equals(playing)) events.motionStarted(token, name);
                  });
            }

            @Override
            public void onCompleteOfMotionPlay(String name) {
              long token = turn;
              post(
                  source,
                  () -> {
                    if (name.equals(playing)) events.motionDone(token, name, null);
                  });
            }

            @Override
            public void onStopOfMotionPlay(String name) {
              post(
                  source,
                  () -> {
                    // This service sends play_stop before motion_complete on normal playback.
                    // Explicit user cancellation is already handled by the controller token.
                    // Wait for completion/error; an isolated stop is bounded by the output timeout.
                    if (name.equals(playing))
                      android.util.Log.i("KebbiSdk", "motion_stop_notification:" + name);
                  });
            }

            @Override
            public void onErrorOfMotionPlay(int code) {
              long token = turn;
              String id = playing;
              post(source, () -> events.motionDone(token, id, "motion_error"));
            }
          });
      main.postDelayed(
          () -> {
            if (source == epoch && !ready && !closed) events.connected(false);
          },
          15000);
    } catch (RuntimeException error) {
      if (events != null) events.connected(false);
    }
  }

  private void serviceReady(long source) {
    if (source != epoch || api == null) return;
    ready = true;
    events.connected(true);
    refreshMotions();
  }

  private void requireReady() {
    if (!ready || api == null) throw new IllegalStateException("sdk_unavailable");
  }

  private void postVoice(long source,long generation,Runnable action) {
    post(source,()->{ if (generation==voiceGeneration) action.run(); });
  }

  private void callbacks(long token) {
    requireReady();
    turn = token;
    long source = epoch;
    long generation=++voiceGeneration;
    api.registerVoiceEventListener(
        new VoiceEventCallback() {
          @Override
          public void onSpeech2TextComplete(boolean error, String raw) {
            postVoice(
                source, generation,
                () -> {
                  String result = "";
                  if (!error)
                    try {
                      result = new org.json.JSONObject(raw).optString("result", "");
                    } catch (Exception ignored) {
                    }
                  events.asr(token, result, error ? "asr_error" : null);
                });
          }

          @Override
          public void onTTSComplete(boolean error) {
            postVoice(source, generation, () -> events.ttsDone(token, error ? "tts_error" : null));
          }

          @Override
          public void onSpeakState(
              VoiceEventListener.SpeakType type, VoiceEventListener.SpeakState state) {
            if (state == VoiceEventListener.SpeakState.START)
              postVoice(source, generation, () -> events.ttsStarted(token));
          }
        });
  }

  public void listen(long token, String language) {
    callbacks(token);
    api.setListenParameter(
        VoiceEventListener.ListenType.RECOGNIZE,
        "language",
        language.equals("ja") ? "ja-JP" : "en-US");
    api.startSpeech2Text(false);
  }

  public void stopListening() {
    if (ready && api != null) api.stopListen();
  }

  public void speak(long token, String text, String language) {
    callbacks(token);
    api.startTTS(text, language.equals("ja") ? NuwaRobotAPI.JAPAN : NuwaRobotAPI.ENGLISH);
  }

  public void play(long token, Motion motion) {
    requireReady();
    turn = token;
    playing = motion.id;
    api.motionPlay(motion.id, motion.showMp4);
  }

  public boolean supportsSentenceOutput() { return true; }

  public void outputSentence(long token,Motion motion,String text,String language) {
    callbacks(token);playing=motion.id;
    PreparedSentence item=new PreparedSentence(token,epoch,motion,text,language);prepared=item;
    api.motionMediaDisable(!motion.showMp4);
    android.util.Log.i("KebbiSdk","sentence_motion_prepare_request:"+motion.id);
    api.motionPrepare(motion.id);
    main.postDelayed(()->{
      if (prepared!=item || item.source!=epoch || closed) return;
      prepared=null;
      try { api.motionStop(false); } catch (RuntimeException ignored) {}
      events.motionDone(item.token,item.motion.id,"motion_prepare_timeout");
      speakPrepared(item);
    },1800);
  }

  private void speakPrepared(PreparedSentence item) {
    if (closed || item.source!=epoch || item.token!=turn || api==null || !ready) return;
    android.util.Log.i("KebbiSdk","sentence_tts_dispatch");
    api.startTTS(item.text,item.language.equals("ja")?NuwaRobotAPI.JAPAN:NuwaRobotAPI.ENGLISH);
  }

  @Override public void finishSentence() {
    prepared=null;voiceGeneration++;turn=-1;playing="";
    if (api==null || !ready) return;
    try { api.motionStop(false); } catch (RuntimeException ignored) {}
    try { api.hideWindow(false); } catch (RuntimeException ignored) {}
    try { api.motionMediaDisable(false); } catch (RuntimeException ignored) {}
    // Keep this SDK binding. Voice generations reject the previous sentence's callbacks.
    // Motion callbacks are diagnostic; TTS completion advances the sentence sequence.
  }

  public void refreshMotions() {
    if (!ready || api == null) return;
    long source = epoch;
    api.requestMoitonList();
    poll(source, 0, Collections.emptyList());
  }

  private void poll(long source, int attempt, List<String> previous) {
    main.postDelayed(
        () -> {
          if (source != epoch || !ready || api == null) return;
          List<String> names;
          try {
            List<String> current = api.getMotionList();
            names = current == null ? new ArrayList<>() : new ArrayList<>(current);
            Collections.sort(names);
          } catch (RuntimeException error) {
            names = new ArrayList<>();
          }
          // No list-ready callback is specified by 2.1.0.08. Wait for two equal nonempty samples,
          // bounded to 8s.
          if ((!names.isEmpty() && names.equals(previous)) || attempt >= 31) {
            events.motions(names);
            return;
          }
          poll(source, attempt + 1, names);
        },
        250);
  }

  public void stopAll() {
    prepared=null;voiceGeneration++;
    if (api != null && ready) {
      try {
        api.stopListen();
      } catch (RuntimeException ignored) {
      }
      try {
        api.stopTTS();
      } catch (RuntimeException ignored) {
      }
      try {
        api.motionStop(true);
        api.motionMediaDisable(false);
      } catch (RuntimeException ignored) {
      }
    }
    if (!closed) reset();
  }

  public void finishTurn() {
    if (!closed) reset();
  }

  public void close() {
    closed = true;
    prepared=null;voiceGeneration++;
    ++epoch;
    ready = false;
    if (api != null) {
      try {
        api.stopListen();
        api.stopTTS();
        api.motionStop(true);
        api.motionMediaDisable(false);
      } catch (RuntimeException ignored) {
      }
      try {
        api.release();
      } catch (RuntimeException ignored) {
      }
      api = null;
    }
    main.removeCallbacksAndMessages(null);
    events = null;
  }
}
