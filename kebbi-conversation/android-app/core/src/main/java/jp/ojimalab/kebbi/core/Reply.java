package jp.ojimalab.kebbi.core;

import com.google.gson.*;

public final class Reply {
  public final String speech, language, timing;
  public final Gesture gesture;

  public Reply(String speech, Gesture gesture, String language) {
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
      if (!java.util.Arrays.asList("speech", "gesture", "language", "timing").contains(key))
        throw new IllegalArgumentException("unexpected_field");
    return new Reply(speech, Gesture.safe(gesture), language);
  }

  private static String string(JsonObject o, String key) {
    JsonElement e = o.get(key);
    if (e == null || !e.isJsonPrimitive() || !e.getAsJsonPrimitive().isString())
      throw new IllegalArgumentException("invalid_" + key);
    return e.getAsString();
  }
}
