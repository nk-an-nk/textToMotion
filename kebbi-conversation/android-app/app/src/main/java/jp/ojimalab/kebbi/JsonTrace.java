package jp.ojimalab.kebbi;

import android.content.*;
import android.util.Log;
import com.google.gson.Gson;
import java.io.*;
import java.util.*;
import jp.ojimalab.kebbi.core.RuntimePorts;

public final class JsonTrace implements RuntimePorts.Log {
  private final Context context;
  private final SharedPreferences settings;
  private final ArrayDeque<String> rows = new ArrayDeque<>();
  private final Gson gson = new Gson();

  public JsonTrace(Context context, SharedPreferences settings) {
    this.context = context;
    this.settings = settings;
  }

  public synchronized void event(String turn, String event, Map<String, Object> fields) {
    if (!settings.getBoolean("log", true)) return;
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("conversation_id", turn);
    row.put("event", event);
    row.put("monotonic_ms", android.os.SystemClock.elapsedRealtime());
    row.putAll(fields);
    String line = gson.toJson(row);
    rows.addLast(line);
    while (rows.size() > 100) rows.removeFirst();
    Log.i("KebbiTrace", line);
    if (settings.getBoolean("persist", false))
      try (FileWriter out =
          new FileWriter(
              new File(context.getFilesDir(), "events.jsonl"),
              new File(context.getFilesDir(), "events.jsonl").length() < 5 * 1024 * 1024)) {
        out.write(line + "\n");
      } catch (IOException ignored) {
        Log.w("KebbiTrace", "trace_write_failed");
      }
  }

  public synchronized String text() {
    return String.join("\n", rows);
  }

  public void content(String turn, String user, String speech) {
    if (settings.getBoolean("content", false)) {
      Map<String, Object> fields = new LinkedHashMap<>();
      fields.put("user_text", user);
      fields.put("speech", speech);
      event(turn, "conversation_content", fields);
    }
  }

  public synchronized void clear() {
    rows.clear();
    new File(context.getFilesDir(), "events.jsonl").delete();
  }
}
