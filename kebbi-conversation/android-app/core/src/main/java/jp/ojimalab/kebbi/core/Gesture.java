package jp.ojimalab.kebbi.core;

public enum Gesture {
  greet,
  acknowledge,
  praise,
  surprise,
  explain,
  think,
  question,
  none;

  public static Gesture safe(String label) {
    try {
      return valueOf(label);
    } catch (Exception ignored) {
      return none;
    }
  }
}
