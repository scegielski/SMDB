#version 120

attribute highp vec4 vertex;
uniform highp mat4 matrix;
attribute lowp vec4 color_attr;
attribute vec2 texture_coordinates;

varying lowp vec4 color;
varying vec2 v_texture_coordinates;

void main(void)
{
    v_texture_coordinates = texture_coordinates;
    gl_Position = matrix * vertex;
    color = color_attr;
}