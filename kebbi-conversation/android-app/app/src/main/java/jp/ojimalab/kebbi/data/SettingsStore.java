package jp.ojimalab.kebbi.data;

import android.content.Context;
import android.content.SharedPreferences;
import jp.ojimalab.kebbi.core.SelectionOptions;

/** Persists the settings used by the existing app installations. */
public final class SettingsStore {
  public static final class ConnectionSettings {
    public final String url, token, language, mockFault;
    public final boolean motion, log, persist, content;

    public ConnectionSettings(String url, String token, String language, boolean motion,
        boolean log, boolean persist, boolean content, String mockFault) {
      this.url = url;
      this.token = token;
      this.language = language;
      this.motion = motion;
      this.log = log;
      this.persist = persist;
      this.content = content;
      this.mockFault = mockFault;
    }
  }

  private final SharedPreferences prefs;

  public SettingsStore(Context context) {
    prefs = context.getSharedPreferences("kebbi", Context.MODE_PRIVATE);
  }

  public ConnectionSettings connection() {
    return new ConnectionSettings(prefs.getString("url", "http://10.0.2.2:8000"),
        prefs.getString("token", ""), language(),
        prefs.getBoolean("motion", true), prefs.getBoolean("log", true),
        prefs.getBoolean("persist", false), prefs.getBoolean("content", false),
        prefs.getString("mock_fault", "none"));
  }

  public void saveConnection(ConnectionSettings settings) {
    prefs.edit().putString("url", settings.url).putString("token", settings.token)
        .putString("language", settings.language).putBoolean("motion", settings.motion)
        .putBoolean("log", settings.log).putBoolean("persist", settings.persist)
        .putBoolean("content", settings.content).putString("mock_fault", settings.mockFault).apply();
  }

  public void setLanguage(String language) {
    prefs.edit().putString("language", language).apply();
  }

  public String language() {
    return "ja".equals(prefs.getString("language", "en")) ? "ja" : "en";
  }

  public int experiment() {
    int value = prefs.getInt("experiment", 0);
    return value >= 0 && value <= 2 ? value : 0;
  }

  public void setExperiment(int index) {
    prefs.edit().putInt("experiment", index).apply();
  }

  public String replyModel() {
    String defaultModel = SelectionOptions.REPLY_MODELS.get(0);
    String value = prefs.getString("reply_model", defaultModel);
    return SelectionOptions.REPLY_MODELS.contains(value) ? value : defaultModel;
  }

  public void setReplyModel(String model) {
    prefs.edit().putString("reply_model", model).apply();
  }

  SharedPreferences preferences() {
    return prefs;
  }
}
