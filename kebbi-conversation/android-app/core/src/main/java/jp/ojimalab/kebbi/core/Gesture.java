package jp.ojimalab.kebbi.core;

public enum Gesture {
  greet,
  acknowledge,
  praise,
  surprise,
  explain,
  think,
  question,
  joy, empathy, encourage, apologize, farewell, confused, excited, calm,
  sadness, anger, fear, disgust, affection, animal, dance, exercise, daily_action, movement,
  none;

  public static boolean basic(Gesture g) {
    return g.ordinal() <= question.ordinal() || g == none;
  }

  public static Gesture safe(String label) {
    try {
      return valueOf(label);
    } catch (Exception ignored) {
      return none;
    }
  }
}
