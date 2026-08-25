import sublime


_PANEL_NAME = "avalonia"


def output_panel(window):

    panel = window.create_output_panel(_PANEL_NAME)

    settings = panel.settings()

    settings.set("line_numbers", False)
    settings.set("gutter", False)
    settings.set("word_wrap", False)

    return panel


def clear(window):

    panel = output_panel(window)

    panel.run_command(
        "select_all"
    )

    panel.run_command(
        "right_delete"
    )


def append(window, text):

    panel = output_panel(window)

    panel.set_read_only(False)

    panel.run_command(
        "append",
        {
            "characters": text
        }
    )

    panel.set_read_only(True)

    window.run_command(
        "show_panel",
        {
            "panel": f"output.{_PANEL_NAME}"
        }
    )
