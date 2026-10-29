package jp.ojimalab.kebbi.core;

public final class Motion {
  public String id, scene = "";
  public long durationMs = 4000, cooldownMs = 5000;
  public boolean showMp4 = false, enabled = true, basicOnly = false;

  public Motion(String id) {
    this.id = id;
  }

  public Motion() {}

  public boolean valid() {
    return id != null
        && !id.trim().isEmpty()
        && id.length() <= 200
        && scene != null && scene.length() <= 200
        && !scene.matches("(?s).*[\\p{Cntrl}].*")
        && !id.matches("(?s).*[\\p{Cntrl}].*")
        && durationMs >= 0
        && durationMs <= 60000
        && cooldownMs >= 0
        && cooldownMs <= 3600000;
  }
}
