#version 120
varying vec3 fragNormal;
varying vec3 fragPosition;
varying vec3 fragWorldPosition;
varying vec2 fragTexCoord;
varying vec4 fragColor;

void main() {
    // Transform vertex position to view space
    fragPosition = vec3(gl_ModelViewMatrix * gl_Vertex);
    
    // Pass world position for procedural texturing
    fragWorldPosition = gl_Vertex.xyz;
    
    // Transform normal to view space
    fragNormal = normalize(gl_NormalMatrix * gl_Normal);
    
    // Pass through texture coordinates
    fragTexCoord = vec2(gl_MultiTexCoord0);
    
    // Pass through vertex color
    fragColor = gl_Color;
    
    // Transform vertex to clip space
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
