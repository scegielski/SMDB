#version 120

uniform sampler2D texture1;
varying vec2 v_texture_coordinates;
varying lowp vec4 color;

void main(void)
{
    gl_FragColor = color;
    gl_FragColor = texture2D(texture1, v_texture_coordinates);
}