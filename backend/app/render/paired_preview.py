"""Share decoding and composition between clean and subtitled review videos."""

from pathlib import Path

from app.render.filters import ass_filter


def paired_preview_command(
    command: list[str], *, live_output_path: str | Path,
    subtitle_path: str | Path | None,
) -> list[str]:
    """Extend the short renderer's clean-video command with a second output.

    Both outputs retain the production dimensions, frame rate and encoder
    settings. Only the expensive source/crop/blur/banner graph is shared.
    """
    filter_flag = "-filter_complex" if "-filter_complex" in command else "-vf"
    filter_index = command.index(filter_flag)
    graph = command[filter_index + 1]
    prefix = command[:filter_index]
    tail = command[filter_index + 2:-1]
    # The simple-filter command places maps before -vf.
    maps: list[str] = []
    for args in (prefix, tail):
        while "-map" in args:
            index = args.index("-map")
            maps.append(args[index + 1])
            del args[index:index + 2]
    video_map, *audio_maps = maps
    if filter_flag == "-vf":
        graph = f"[{video_map}]{graph}[paired_base]"
        video_map = "[paired_base]"
    graph += f";{video_map}split=2[paired_clean][paired_text]"
    text_filter = ass_filter(subtitle_path) if subtitle_path is not None else "null"
    graph += f";[paired_text]{text_filter}[paired_exact]"
    exact_audio: list[str] = []
    live_audio: list[str] = []
    for index, audio_map in enumerate(audio_maps):
        if audio_map.startswith("["):
            # A prepended hook has a filtered/concatenated audio stream.
            graph += f";{audio_map}asplit=2[paired_audio{index}a][paired_audio{index}b]"
            exact_audio += ["-map", f"[paired_audio{index}a]"]
            live_audio += ["-map", f"[paired_audio{index}b]"]
        else:
            exact_audio += ["-map", audio_map]
            live_audio += ["-map", audio_map]
    # -t following the last input is an output option: apply it to BOTH
    # files, otherwise looped banner images could make the second file endless.
    last_input = max(i for i, arg in enumerate(prefix) if arg == "-i")
    output_options = prefix[last_input + 2:]
    prefix = prefix[:last_input + 2]
    options = output_options + tail
    return [
        *prefix, "-filter_complex", graph,
        "-map", "[paired_exact]", *exact_audio, *options, command[-1],
        "-map", "[paired_clean]", *live_audio, *options, str(live_output_path),
    ]
