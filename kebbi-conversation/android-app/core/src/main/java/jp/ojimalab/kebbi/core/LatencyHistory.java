package jp.ojimalab.kebbi.core;

import com.google.gson.*;
import java.text.SimpleDateFormat;
import java.util.*;

/** Bounded metadata-only records. No utterances, replies, URLs or credentials. */
public final class LatencyHistory {
  public static final int LIMIT = 200;
  private static final List<String> KEYS = Arrays.asList("asr_ms", "llm_ms", "reply_latency_ms",
      "speech_latency_ms", "motion_latency_ms", "turn_ms", "start_difference_ms", "text_generation_ms", "motion_selection_ms");
  private final LinkedHashMap<String, Entry> rows = new LinkedHashMap<>();

  public static final class Entry {
    public String turnId, mode, profile, input, language, status, errorCode, motionId;
    public String replyModel, motionModel, replyReasoningEffort;
    public long recordedAt;
    public int sentenceCount;
    public List<String> motionIds = new ArrayList<>();
    public Map<String, Long> timings = new LinkedHashMap<>();
  }

  public void record(String turn, Map<String, Object> fields, long recordedAt) {
    UUID.fromString(turn);
    Entry e = new Entry();
    e.turnId = turn;
    e.recordedAt = recordedAt;
    e.mode = allowed(fields.get("selection_mode"), "category", "category", "direct");
    e.profile = allowed(fields.get("gesture_profile"), "basic", "basic", "expanded");
    e.input = allowed(fields.get("input_mode"), "unknown", "conversation_voice", "conversation_text", "asr_only", "tts_only", "tts_motion", "motion_only");
    e.language = allowed(fields.get("language"), "unknown", "en", "ja");
    e.status = allowed(fields.get("status"), "completed", "completed", "partial", "error", "cancelled");
    e.errorCode = text(fields.get("error_code"), 80);
    e.motionId = text(fields.get("motion_id"), 200);
    e.replyModel = model(fields.get("reply_model"));
    e.motionModel = model(fields.get("motion_model"));
    e.replyReasoningEffort = allowed(fields.get("reply_reasoning_effort"), "", "none", "low");
    Object count=fields.get("sentence_count");
    if (count instanceof Number) e.sentenceCount=Math.max(0,Math.min(6,((Number)count).intValue()));
    Object ids=fields.get("motion_ids");
    if (ids instanceof List<?>) for (Object id : (List<?>)ids) {
      String safe=text(id,200); if (!safe.isEmpty() && e.motionIds.size()<6) e.motionIds.add(safe);
    }
    for (String key : KEYS) {
      Object value = fields.get(key);
      if (!(value instanceof Number)) continue;
      double d = ((Number) value).doubleValue();
      if (Double.isNaN(d) || Double.isInfinite(d) || d != Math.rint(d) || Math.abs(d) > 86400000
          || (d < 0 && !key.equals("start_difference_ms"))) continue;
      e.timings.put(key, ((Number) value).longValue());
    }
    rows.remove(turn);
    rows.put(turn, e);
    while (rows.size() > LIMIT) rows.remove(rows.keySet().iterator().next());
  }

  private static String allowed(Object value, String fallback, String... values) {
    return value instanceof String && Arrays.asList(values).contains(value) ? (String) value : fallback;
  }

  private static String model(Object value) {
    return value instanceof String && ((String)value).matches("[A-Za-z0-9._-]{1,100}") ? (String)value : "";
  }

  private static String text(Object value, int limit) {
    String s = value instanceof String ? (String) value : "";
    return s.length() <= limit ? s.replaceAll("[\\p{Cntrl}]", " ") : "";
  }

  public List<Entry> entries() { return Collections.unmodifiableList(new ArrayList<>(rows.values())); }
  public Entry latest() { return rows.isEmpty() ? null : new ArrayList<>(rows.values()).get(rows.size()-1); }
  public void clear() { rows.clear(); }
  public String json() { return new Gson().toJson(rows.values()); }

  public static LatencyHistory parse(String json) {
    LatencyHistory history = new LatencyHistory();
    for (JsonElement row : JsonParser.parseString(json).getAsJsonArray()) {
      try {
        Entry e = new Gson().fromJson(row, Entry.class);
        Map<String, Object> fields = new LinkedHashMap<>();
        if (e.timings != null) fields.putAll(e.timings);
        fields.put("selection_mode", e.mode); fields.put("gesture_profile", e.profile);
        fields.put("input_mode", e.input); fields.put("language", e.language); fields.put("status", e.status);
        fields.put("error_code", e.errorCode); fields.put("motion_id", e.motionId);
        fields.put("sentence_count", e.sentenceCount); fields.put("motion_ids", e.motionIds);
        fields.put("reply_model", e.replyModel); fields.put("motion_model", e.motionModel);
        fields.put("reply_reasoning_effort", e.replyReasoningEffort);
        history.record(e.turnId, fields, e.recordedAt);
      } catch (RuntimeException ignored) { /* Recover other valid records. */ }
    }
    return history;
  }

  private static String seconds(Long n) { return n == null ? "—" : String.format(Locale.JAPAN, "%.3f秒", n/1000.0); }
  private static String condition(Entry e) { return e.mode.equals("direct") ? "① ID直接" : "② カテゴリ" + (e.profile.equals("expanded") ? "25種" : "7種"); }
  private static String input(Entry e) { return (e.input.equals("conversation_voice") ? "音声会話" : e.input.equals("conversation_text") ? "テキスト会話" : e.input) + "・" + ("ja".equals(e.language) ? "日本語" : "en".equals(e.language) ? "英語" : "言語未記録"); }
  private static String time(Entry e) { return new SimpleDateFormat("MM/dd HH:mm:ss", Locale.JAPAN).format(new Date(e.recordedAt)); }
  private static String values(Entry e) {
    return (e.replyModel.isEmpty() ? "" : "文章生成 " + seconds(e.timings.get("text_generation_ms"))
        + " / 動作選択 " + seconds(e.timings.get("motion_selection_ms")) + "\n")
        + "LLM全体待ち " + seconds(e.timings.get("llm_ms"))
        + " / 返答開始 " + seconds(e.timings.get("reply_latency_ms"))
        + "\nASR " + seconds(e.timings.get("asr_ms"))
        + " / 操作→発声 " + seconds(e.timings.get("speech_latency_ms"))
        + " / 全体 " + seconds(e.timings.get("turn_ms"));
  }

  public String latestText() {
    Entry e = latest();
    return e == null ? "返答速度: まだ記録がありません" : "最新の返答速度（" + condition(e) + "・" + input(e) + "）\n"
        + modelCondition(e) + "\n" + values(e) + "\n" + time(e) + " / " + e.status + (e.sentenceCount>0 ? " / " + e.sentenceCount + "文" : "");
  }

  private static String modelCondition(Entry e) {
    return e.replyModel.isEmpty() ? "従来・一括生成" : "返答 " + e.replyModel + " / 推論 " + (e.replyReasoningEffort.isEmpty() ? "未記録" : e.replyReasoningEffort)
        + " / 動作 " + (e.motionModel.isEmpty() ? "未計測" : e.motionModel);
  }

  /** Averages never mix input paths, failures or non-conversation diagnostics. */
  public String summaryText() {
    Map<String, List<Entry>> groups = new LinkedHashMap<>();
    int failed = 0;
    for (Entry e : rows.values()) {
      if (!e.status.equals("completed")) failed++;
      if (!e.status.equals("completed") || !e.input.startsWith("conversation_")) continue;
      String key = condition(e) + "・" + input(e) + "\n" + modelCondition(e);
      groups.computeIfAbsent(key, k -> new ArrayList<>()).add(e);
    }
    StringBuilder out = new StringBuilder("記録 " + rows.size() + "件（最大200件） / 未完了・一部失敗 " + failed + "件\n条件別平均（成功会話のみ・入力別）\n");
    for (Map.Entry<String,List<Entry>> group : groups.entrySet()) {
      out.append("\n").append(group.getKey()).append(" / ").append(group.getValue().size()).append("件\n");
      for (String key : Arrays.asList("text_generation_ms", "motion_selection_ms", "llm_ms", "reply_latency_ms")) {
        long sum = 0; int count = 0;
        for (Entry e : group.getValue()) if (e.timings.containsKey(key)) { sum += e.timings.get(key); count++; }
        out.append(key.equals("text_generation_ms") ? "文章生成 " : key.equals("motion_selection_ms") ? "動作選択 " : key.equals("llm_ms") ? "LLM全体待ち " : "返答開始 ").append(count == 0 ? "—" : seconds(Math.round((double)sum/count))).append("（n=").append(count).append("） ");
      }
      out.append("\n");
    }
    return out.toString();
  }

  public String historyText() {
    StringBuilder out = new StringBuilder(summaryText());
    List<Entry> reversed = new ArrayList<>(rows.values()); Collections.reverse(reversed);
    for (Entry e : reversed) out.append("\n────────\n").append(time(e)).append(" / ").append(condition(e)).append(" / ").append(input(e)).append(" / ").append(e.status)
        .append("\n").append(modelCondition(e)).append("\n").append(values(e)).append("\nID: ").append(e.motionId.isEmpty()?"なし":e.motionId)
        .append(e.motionIds.isEmpty()?"":"\n文の動作ID: "+String.join(" / ",e.motionIds))
        .append(e.errorCode.isEmpty()?"":"\n"+e.errorCode);
    return out.toString();
  }

  private static String csvCell(String s) {
    if (s == null) s = "";
    if (!s.isEmpty() && "=+-@\t\r".indexOf(s.charAt(0)) >= 0) s = "'" + s;
    return "\"" + s.replace("\"", "\"\"") + "\"";
  }

  public String csv() {
    StringBuilder out = new StringBuilder("recorded_at_epoch_ms,conversation_id,selection_mode,gesture_profile,input_mode,language,status,error_code,motion_id,sentence_count,motion_ids,reply_model,motion_model,reply_reasoning_effort");
    for (String key : KEYS) out.append(',').append(key);
    out.append("\r\n");
    for (Entry e : rows.values()) {
      out.append(e.recordedAt);
      for (String s : Arrays.asList(e.turnId,e.mode,e.profile,e.input,e.language,e.status,e.errorCode,e.motionId,Integer.toString(e.sentenceCount),String.join("|",e.motionIds),e.replyModel,e.motionModel,e.replyReasoningEffort)) out.append(',').append(csvCell(s));
      for (String key : KEYS) out.append(',').append(e.timings.containsKey(key)?e.timings.get(key):"");
      out.append("\r\n");
    }
    return out.toString();
  }
}
