from reportlab.lib import colors


def get_sda_cell_color(val: float):
    val = float(val)
    if val >= 75:
        return colors.Color(0, 255 / 255, 0, 0.3)
    elif val >= 55:
        return colors.Color(85 / 255, 255 / 255, 0, 0.3)
    elif val >= 40:
        return colors.Color(170 / 255, 255 / 255, 0, 0.3)
    else:
        return colors.Color(255 / 255, 170 / 255, 0, 0.3)


def get_ase_cell_color(val: float):
    val = float(val)
    if val > 10:
        return colors.Color(255 / 255, 170 / 255, 0, 0.3)
    else:
        return colors.Color(0, 255 / 255, 0, 0.3)
