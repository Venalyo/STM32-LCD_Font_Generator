from PIL import Image, ImageFont, ImageDraw
import argparse
import math
import re
import time
import textwrap
import regex

# Greyscale threshold from 0 - 255
THRESHOLD = 128
# Font Character Set
CHAR_SET = r' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~'


def get_charset_perceived():
    # https://stackoverflow.com/questions/6805311/playing-around-with-devanagari-characters
    return regex.findall(r'\X', CHAR_SET)


def get_font_sizes(font):
    widths = []
    heights = []
    for ch in get_charset_perceived():
        _, _, w, h = font.getbbox(ch)
        widths.append(w)
        heights.append(h)
    return widths, heights


def bin_to_c_hex_array(bin_text, bytes_per_line, lsb_padding=0, msb_padding=0):
    # create comment with preview of line
    comment = bin_text.replace('0', ' ').replace('1', '#')

    # pad the top or bottom remaining bits with 0's
    bin_text = ("0" * msb_padding) + bin_text + ("0" * lsb_padding)
    # ensure the length matches the number of bytes
    assert len(bin_text) == (bytes_per_line * 8)

    # split up into 8 digits each of bytes
    bin_list = re.findall('.{8}', bin_text)
    # convert to hex representation
    bin_list = map(lambda a: "0x{:02X}".format(int(a, 2)), bin_list)
    array = ', '.join(bin_list)

    return f'{array}, /* |{comment}| */\n'


def generate_font_data(font, x_size, y_size):
    data = ''

    # find bytes per line needed to fit the font width
    bytes_per_line = math.ceil(x_size / 8)
    empty_bit_padding = (bytes_per_line * 8 - x_size)

    for i, ch in enumerate(get_charset_perceived()):
        # the starting array index of the current char
        array_offset = i * (bytes_per_line * y_size)
        assert data.count('0x') == array_offset

        # comment separator for each char
        data += '\n'
        data += f"// @{array_offset} '{ch}' ({x_size} pixels wide)\n"

        # Calculate size and margins for centered text
        _, _, w, h = font.getbbox(ch)
        x_margin = (x_size - w) // 2
        y_margin = 0  # (y_size - h) // 2
        margin = (x_margin, y_margin)
        im_size = (x_size, y_size)

        # create image and write the char
        im = Image.new("RGB", im_size)
        drawer = ImageDraw.Draw(im)
        drawer.text(margin, ch, font=font)
        del drawer

        # for each row, convert to hex representation
        for y in range(y_size):
            # get list of row pixels
            x_coordinates = range(x_size)
            pixels = map(lambda x: im.getpixel((x, y))[0], x_coordinates)
            # convert to bin text
            bin_text = map(lambda val: '1' if val > THRESHOLD else '0', pixels)
            bin_text = ''.join(bin_text)
            # convert to c-style hex array
            data += bin_to_c_hex_array(bin_text, bytes_per_line,
                                       lsb_padding=empty_bit_padding)
    return data


def output_files(font, font_widths, font_height, font_size, font_data, font_name):
    generated_time = time.strftime("%Y-%m-%d %H:%M:%S")

    # create filename, remove invalid chars
    filename = f'Font{font_name}{font_size}'
    filename = ''.join(c if c.isalnum() else '' for c in filename)

    # C file template
    output = f"""/**
 * This file provides '{font_name}' [{font_size}px] text font
 * for STM32xx-EVAL's LCD driver.
 *
 * Generated on {generated_time}
 */
#pragma once

#include "fonts.h"

#define {filename}_Name ("{font_name} {font_size}px")

// {font_data.count('0x')} bytes
const uint8_t {filename}_Table [] = {{{font_data}}};

const uint8_t {filename}_Width [] = {{
    {", ".join([str(w) for w in font_widths])}
}};

const uint8_t {filename}_LeftMargin [] = {{
    {", ".join([str((max(font_widths) - w) // 2) for w in font_widths])}
}};

swFONT {filename}_w = {{
    {filename}_Table,
    {max(font_widths)}, /* Width */
    {font_height}, /* Height */
    {filename}_Width,
    {filename}_LeftMargin,
}};
sFONT {filename} = {{
    {filename}_Table,
    {max(font_widths)}, /* Width */
    {font_height}, /* Height */
}};
"""
    # Output font C header file
    with open(f'{filename}.h', 'w') as f:
        f.write(output)

    # # Output preview of font
    # _, _, w, h = font.getbbox(CHAR_SET)
    # size = (w, h)
    # im = Image.new("RGB", size)
    # drawer = ImageDraw.Draw(im)
    # drawer.text((0, 0), CHAR_SET, font=font)
    # im.save(f'{filename}.png')


if __name__ == '__main__':
    # Command-line arguments
    parser = argparse.ArgumentParser(
        description='Generate text font for STM32xx-EVAL\'s LCD driver')

    parser.add_argument('-f', '--font',
                        type=str,
                        help='Font type [filename]',
                        required=True)
    parser.add_argument('-s', '--size',
                        type=int,
                        help='Font size in pixels [int]',
                        default=16,
                        required=False)
    parser.add_argument('-n', '--name',
                        type=str,
                        help='Custom font name [str]',
                        required=False)
    parser.add_argument('-c', '--charset',
                        type=str,
                        help='Custom charset from file [filename]',
                        required=False)
    parser.add_argument('-t', '--threshold',
                        type=int,
                        help='Greyscale threshold from 0 - 255',
                        default=128,
                        required=False)
    args = parser.parse_args()

    if args.charset:
        with open(args.charset, encoding="utf-8") as f:
            CHAR_SET = f.read().splitlines()[0]

    THRESHOLD = args.threshold

    # create font type
    font_type = args.font
    font_size = args.size

    myfont = ImageFont.truetype(font_type, size=font_size)
    font_widths, font_heights = get_font_sizes(myfont)

    # while max(font_heights) > args.size:
    #     myfont = ImageFont.truetype(font_type, size=myfont.size - 1)
    #     font_widths, font_heights = get_font_sizes(myfont)

    if args.name:
        font_name = args.name
    else:
        font_name = myfont.font.family

    # generate the C file data
    font_data = generate_font_data(myfont, max(font_widths), max(font_heights))
    font_data = textwrap.indent(font_data, ' ' * 4)

    # output everything
    output_files(font=myfont,
                 font_widths=font_widths,
                 font_height=max(font_heights), 
                 font_size=font_size,
                 font_data=font_data,
                 font_name=font_name)
