from reportlab.lib import colors


def get_sda_cell_color(val: float):
    val = float(val)
    if val >= 75:
        return colors.Color(179 / 255, 255 / 255, 179 / 255)
    elif val >= 55:
        return colors.Color(204 / 255, 255 / 255, 179 / 255)
    elif val >= 40:
        return colors.Color(230 / 255, 255 / 255, 179 / 255)
    else:
        return colors.Color(255 / 255, 230 / 255, 179 / 255)


def get_ase_cell_color(val: float):
    val = float(val)
    if val > 10:
        return colors.Color(255 / 255, 230 / 255, 179 / 255)
    else:
        return colors.Color(179 / 255, 255 / 255, 179 / 255)
