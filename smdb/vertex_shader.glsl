#version 120
varying vec3 fragNormal;
varying vec3 fragPosition;
varying vec3 fragWorldPosition;
varying vec2 fragTexCoord;
varying vec4 fragColor;
varying vec3 fragTangent;
varying vec3 fragBitangent;
varying vec4 fragShadowCoord;

uniform mat4 shadowMatrix;
uniform mat4 lightViewMatrix;
uniform mat4 lightProjMatrix;

void main() {
    // Transform vertex position to view space
    fragPosition = vec3(gl_ModelViewMatrix * gl_Vertex);
    
    // Pass world position for procedural texturing
    fragWorldPosition = gl_Vertex.xyz;
    
    // Transform normal to view space
    fragNormal = normalize(gl_NormalMatrix * gl_Normal);
    
    // Compute tangent and bitangent for potential normal mapping
    // For now, we'll derive them from the normal
    vec3 c1 = cross(gl_Normal, vec3(0.0, 0.0, 1.0));
    vec3 c2 = cross(gl_Normal, vec3(0.0, 1.0, 0.0));
    vec3 tangent = length(c1) > length(c2) ? c1 : c2;
    fragTangent = normalize(gl_NormalMatrix * tangent);
    fragBitangent = cross(fragNormal, fragTangent);
    
    // Pass through texture coordinates
    fragTexCoord = vec2(gl_MultiTexCoord0);
    
    // Pass through vertex color
    fragColor = gl_Color;
    
    // Calculate shadow coordinates directly in light space
    vec4 worldPos = gl_Vertex;
    vec4 lightSpacePos = lightProjMatrix * lightViewMatrix * worldPos;
    // Apply bias to transform from [-1,1] to [0,1]
    fragShadowCoord.x = lightSpacePos.x * 0.5 + lightSpacePos.w * 0.5;
    fragShadowCoord.y = lightSpacePos.y * 0.5 + lightSpacePos.w * 0.5;
    fragShadowCoord.z = lightSpacePos.z * 0.5 + lightSpacePos.w * 0.5;
    fragShadowCoord.w = lightSpacePos.w;
    
    // Transform vertex to clip space
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
