package jp.ojimalab.kebbi.core;

import com.google.gson.*;
import java.util.*;

public final class Reply {
  public final String speech, language, timing, motionId;
  public final Gesture gesture;
  public final List<Sentence> sentences;
  public final boolean sentencePlan;
  public final Map<String, Object> generation;

  public static final class Sentence {
    public final String speech, motionId;
    public final Gesture gesture;
    public Sentence(String speech, Gesture gesture, String motionId) {
      if (speech == null || speech.trim().isEmpty() || speech.length()>400) throw new IllegalArgumentException("invalid_sentence");
      if (motionId != null && (motionId.trim().isEmpty() || motionId.length()>200)) throw new IllegalArgumentException("invalid_motion_id");
      this.speech=speech.trim();this.gesture=gesture;this.motionId=motionId;
    }
  }

  public Reply(String speech, Gesture gesture, String language) {
    this(speech, gesture, language, null);
  }

  public Reply(String speech, Gesture gesture, String language, String motionId) {
    this(speech, gesture, language, motionId, null);
  }

  public Reply(String speech, Gesture gesture, String language, String motionId, List<Sentence> sentences) {
    this(speech, gesture, language, motionId, sentences, Collections.emptyMap());
  }

  private Reply(String speech, Gesture gesture, String language, String motionId, List<Sentence> sentences, Map<String, Object> generation) {
    this.generation = Collections.unmodifiableMap(new LinkedHashMap<>(generation));
    if (sentences != null && (sentences.isEmpty() || sentences.size()>6)) throw new IllegalArgumentException("invalid_sentences");
    this.sentencePlan=sentences!=null;
    this.sentences=Collections.unmodifiableList(sentences==null ? Collections.singletonList(new Sentence(speech, gesture, motionId)) : new ArrayList<>(sentences));
    if (motionId != null && (motionId.trim().isEmpty() || motionId.length() > 200))
      throw new IllegalArgumentException("invalid_motion_id");
    this.motionId = motionId;
    if (speech == null || speech.trim().isEmpty() || speech.length() > 400)
      throw new IllegalArgumentException("invalid_speech");
    if (!"en".equals(language) && !"ja".equals(language))
      throw new IllegalArgumentException("invalid_language");
    this.speech = speech.trim();
    this.gesture = gesture;
    this.language = language;
    this.timing = "speech_start";
  }

  public static Reply parse(String json) {
    JsonObject o = JsonParser.parseString(json).getAsJsonObject();
    String speech = string(o, "speech"),
        gesture = string(o, "gesture"),
        language = string(o, "language");
    if (!"speech_start".equals(string(o, "timing")))
      throw new IllegalArgumentException("invalid_timing");
    for (String key : o.keySet())
      if (!java.util.Arrays.asList("speech", "gesture", "language", "timing", "motion_id", "sentences", "reply_model", "motion_model", "text_generation_ms", "motion_selection_ms", "reply_reasoning_effort").contains(key))
        throw new IllegalArgumentException("unexpected_field");
    String id = !o.has("motion_id") || o.get("motion_id").isJsonNull() ? null : string(o, "motion_id");
    List<Sentence> sentences=null;
    if (o.has("sentences") && !o.get("sentences").isJsonNull()) {
      sentences=new ArrayList<>();
      for (JsonElement e : o.getAsJsonArray("sentences")) {
        JsonObject item=e.getAsJsonObject();
        for (String key : item.keySet()) if (!Arrays.asList("speech","gesture","motion_id").contains(key)) throw new IllegalArgumentException("unexpected_sentence_field");
        String motionId=!item.has("motion_id") || item.get("motion_id").isJsonNull() ? null : string(item,"motion_id");
        sentences.add(new Sentence(string(item,"speech"),Gesture.safe(string(item,"gesture")),motionId));
      }
      String joined=String.join(language.equals("en") ? " " : "", sentences.stream().map(item -> item.speech).toArray(String[]::new));
      if (!joined.equals(speech)) throw new IllegalArgumentException("sentence_speech_mismatch");
    }
    Map<String, Object> generation = new LinkedHashMap<>();
    for (String key : Arrays.asList("reply_model", "motion_model")) if (o.has(key)) {
      String model = string(o, key);
      if (!model.matches("[A-Za-z0-9._-]{1,100}")) throw new IllegalArgumentException("invalid_model");
      generation.put(key, model);
    }
    for (String key : Arrays.asList("text_generation_ms", "motion_selection_ms")) if (o.has(key)) {
      JsonElement value = o.get(key);
      if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()) throw new IllegalArgumentException("invalid_timing");
      double n = value.getAsDouble();
      if (Double.isNaN(n) || Double.isInfinite(n) || n != Math.rint(n) || n < 0 || n > 60000) throw new IllegalArgumentException("invalid_timing");
      generation.put(key, value.getAsLong());
    }
    if (o.has("reply_reasoning_effort")) {
      String effort = string(o, "reply_reasoning_effort");
      if (!Arrays.asList("none", "low").contains(effort)) throw new IllegalArgumentException("invalid_reasoning_effort");
      generation.put("reply_reasoning_effort", effort);
    }
    return new Reply(speech, Gesture.safe(gesture), language, id, sentences, generation);
  }

  private static String string(JsonObject o, String key) {
    JsonElement e = o.get(key);
    if (e == null || !e.isJsonPrimitive() || !e.getAsJsonPrimitive().isString())
      throw new IllegalArgumentException("invalid_" + key);
    return e.getAsString();
  }
}
