package jp.ojimalab.kebbi.core;

import com.google.gson.*;
import java.util.*;

public final class Reply {
  public final String speech, language, timing, motionId;
  public final Gesture gesture;
  public final List<Sentence> sentences;
  public final boolean sentencePlan;

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
      if (!java.util.Arrays.asList("speech", "gesture", "language", "timing", "motion_id", "sentences").contains(key))
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
    return new Reply(speech, Gesture.safe(gesture), language, id, sentences);
  }

  private static String string(JsonObject o, String key) {
    JsonElement e = o.get(key);
    if (e == null || !e.isJsonPrimitive() || !e.getAsJsonPrimitive().isString())
      throw new IllegalArgumentException("invalid_" + key);
    return e.getAsString();
  }
}
