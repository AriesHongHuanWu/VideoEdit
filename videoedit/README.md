# VideoEdit

The [GitHub release](https://github.com/AriesHongHuanWu/VideoEdit/releases/tag/videoedit-italy-rome) stores the original MP4 bytes.

- [Italy — 217 originals](Italy/README.md)
- [Rome — 35 originals](Rome/README.md)
- [Byte counts, hashes and asset URLs](manifest.json)

Two Italy files use two numbered parts. In a cloud Linux shell, combine them in part order. For example:

    cat Italy--DJI_0141.MP4.part01 Italy--DJI_0141.MP4.part02 > DJI_0141.MP4

Compare the restored file's SHA-256 with the manifest.
