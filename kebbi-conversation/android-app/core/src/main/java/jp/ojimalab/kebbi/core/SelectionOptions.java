package jp.ojimalab.kebbi.core;

import java.util.*;

/** Immutable snapshot of candidates offered for one LLM turn. */
public final class SelectionOptions {
  public final String mode, profile;
  public final List<String> gestures;
  public final List<Candidate> motions;

  public static final class Candidate {
    public final String id, description;
    public Candidate(String id, String description) {
      this.id = id;
      this.description = description;
    }
  }

  public SelectionOptions(String mode, String profile, List<String> gestures, List<Candidate> motions) {
    if (!Arrays.asList("category", "direct").contains(mode)
        || !Arrays.asList("basic", "expanded").contains(profile)) throw new IllegalArgumentException();
    this.mode = mode;
    this.profile = profile;
    this.gestures = Collections.unmodifiableList(new ArrayList<>(gestures));
    this.motions = Collections.unmodifiableList(new ArrayList<>(motions));
  }
}
