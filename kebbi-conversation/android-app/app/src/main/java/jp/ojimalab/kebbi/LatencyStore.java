package jp.ojimalab.kebbi;

import android.content.Context;
import android.util.AtomicFile;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import jp.ojimalab.kebbi.core.LatencyHistory;

/** Small app-private history, independent of optional conversation logging. */
public final class LatencyStore {
  private final AtomicFile file;
  public LatencyHistory history = new LatencyHistory();
  public String warning = "";

  public LatencyStore(Context context) {
    file = new AtomicFile(new File(context.getFilesDir(), "latency-history.json"));
    try (InputStream in = file.openRead(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      byte[] buffer = new byte[4096]; int n;
      while ((n = in.read(buffer)) != -1) {
        if (out.size() + n > 1024*1024) throw new IOException();
        out.write(buffer, 0, n);
      }
      history = LatencyHistory.parse(out.toString("UTF-8"));
    } catch (FileNotFoundException ignored) {
    } catch (Exception error) { warning = "過去の速度履歴を読み込めませんでした。"; }
  }

  public void record(String turn, Map<String,Object> fields) {
    history.record(turn, fields, System.currentTimeMillis());
    save();
  }

  public void clear() { history.clear(); save(); }

  private void save() {
    FileOutputStream out = null;
    try {
      out = file.startWrite();
      out.write(history.json().getBytes(StandardCharsets.UTF_8));
      file.finishWrite(out);
      warning = "";
    } catch (IOException error) {
      if (out != null) file.failWrite(out);
      warning = "速度履歴の保存に失敗しました。今回の値は画面・CSVで確認できます。";
    }
  }
}
