package jp.ojimalab.kebbi;

import android.content.Context;
import jp.ojimalab.kebbi.core.*;

public final class RobotFactory {
  public static final boolean REAL = true;

  public static RobotAdapter create(Context context, AndroidScheduler scheduler) {
    return new RealRobotAdapter(context);
  }
}
