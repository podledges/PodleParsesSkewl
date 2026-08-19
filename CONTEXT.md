# PodleParsesSkewl

Review reconstruction of a lecture Recording: what was said, paired with what was shown.

## Language

**Recording**:
The input media file. In v1 that is one MP4.
_Avoid_: video, lecture file, source file

**Lecture**:
One teaching event. In v1 one Recording is one Lecture and one result.
_Avoid_: session, class, course

**Still**:
A visually stable interval of a Recording that is worth showing, plus the representative image taken from it. A deck page is the common case, not a separate type.
_Avoid_: slide, frame, scene, keyframe, screenshot, visual

**Shown**:
The image a reader should see for a Still.
_Avoid_: thumbnail, preview

**Said**:
The spoken words that belong with some interval of the Recording.
_Avoid_: notes, summary, captions

**Transcript**:
The timed speech text of one Recording, from audio or from a sidecar.
_Avoid_: captions, subtitles (those are sidecar formats, not this object)

**Document**:
The structured result of one Lecture: Stills, Transcript, and the links between them. Canonical file: `lecture.json`.
_Avoid_: report, export, output (those are views or folders)

**Report**:
A human-readable view of a Document. The program's plain HTML/Markdown is one Report. `/ezLectures` can produce another.
_Avoid_: Document (the Document is the source; a Report is a view)
