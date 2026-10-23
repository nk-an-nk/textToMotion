package jp.ojimalab.kebbi;

import android.os.*;
import jp.ojimalab.kebbi.core.RuntimePorts;

public final class AndroidScheduler implements RuntimePorts.Scheduler {
  private final Handler handler = new Handler(Looper.getMainLooper());

  public long now() {
    return SystemClock.elapsedRealtime();
  }

  public void execute(Runnable action) {
    if (Looper.myLooper() == Looper.getMainLooper()) action.run();
    else handler.post(action);
  }

  public RuntimePorts.Cancel later(long delay, Runnable action) {
    handler.postDelayed(action, delay);
    return () -> handler.removeCallbacks(action);
  }
}
