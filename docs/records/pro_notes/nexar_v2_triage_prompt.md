<!-- 원본: Pro `work/nexar_v2/triage_prompt.md` -->

# Nexar v2 triage (AFDA Stage 2) — contact + cut-in screening

You screen dashcam videos from sheets that already exist. Only Read images; do not run commands, do not write files.

For each video `<id>` read `C:\Dacon\Dacon_AFDA_Challenge_git\work\nexar_v2\triage\<id>.jpg`.
Each sheet has 30 tiles (6 per row, left→right, top→bottom), frames from about event-116 to event+29 in steps of 5.
Every tile shows `#<frame index>  <seconds>` in yellow. The given `event` is Nexar's time_of_event frame (a hint, not truth).

Roles: the dashcam car (ego) is the suspect; the "victim" is the other car that enters the ego lane and collides with ego.
Nexar positives include collisions AND near-misses, so `no` is common.

Decide per video:
- `contact`: yes (ego visibly makes contact with another vehicle/object: sudden camera jolt, the car fills the view and stops, debris, the vehicle touches the hood), no (near miss: the other vehicle passes/stops without touching), uncertain.
- `contact_frame_approx`: the first tile index where contact appears (only if contact=yes), else null.
- `cut_in`: yes if the other vehicle enters the ego lane from a neighbouring lane / side road within the sheet (before contact); no if it was already ahead in the ego lane the whole time (same-lane rear-end) or the event is not a lane entry (e.g. ego hits a crossing car head-on at an intersection is `cross`); uncertain otherwise. Use values yes/no/cross/uncertain.
- `side`: LEFT or RIGHT as seen on the dashcam screen (where the other vehicle came from), for cut_in yes or cross; else null.
- `confidence`: 0..1 for the contact decision.
- `note`: at most 15 words.

Final answer: ONLY a JSON array, one object per video, keys: video_id, contact, contact_frame_approx, cut_in, side, confidence, note.
