#version 120
varying vec3 fragNormal;
varying vec3 fragPosition;
varying vec3 fragWorldPosition;
varying vec2 fragTexCoord;
varying vec4 fragColor;

uniform sampler2D textureSampler;
uniform bool useTexture;
uniform bool useCheckerboard;    // Enable checkerboard pattern
uniform float checkerboardScale; // Size of checkerboard squares
uniform vec3 lightPosition;      // Spotlight position in view space
uniform vec3 lightDirection;     // Spotlight direction
uniform float spotCutoff;        // Spotlight cone angle (degrees)
uniform float spotExponent;      // Spotlight falloff
uniform vec3 lightDiffuse;       // Light diffuse color
uniform vec3 lightSpecular;      // Light specular color
uniform float materialShininess; // Material shininess
uniform vec3 materialSpecular;   // Material specular color
uniform float constantAtten;     // Constant attenuation
uniform float linearAtten;       // Linear attenuation
uniform float quadraticAtten;    // Quadratic attenuation

void main() {
    // Base color from texture or vertex color
    vec4 baseColor;
    if (useTexture) {
        baseColor = texture2D(textureSampler, fragTexCoord);
    } else {
        baseColor = fragColor;  // Use color from glColor3f/glColor4f
    }
    
    // Apply checkerboard pattern if enabled
    float checkerFactor = 1.0;
    if (useCheckerboard) {
        // Use world position for consistent pattern
        float checkX = floor(fragWorldPosition.x / checkerboardScale);
        float checkZ = floor(fragWorldPosition.z / checkerboardScale);
        float pattern = mod(checkX + checkZ, 2.0);
        // Create checkerboard: dark (0.3) and light (0.7) squares
        checkerFactor = mix(0.3, 0.7, pattern);
        baseColor.rgb *= checkerFactor;
    }
    
    // Normalize the interpolated normal
    vec3 N = normalize(fragNormal);
    
    // Calculate light direction from fragment to light
    vec3 L = lightPosition - fragPosition;
    float distance = length(L);
    L = normalize(L);
    
    // Calculate spotlight effect
    vec3 spotDir = normalize(lightDirection);
    float spotDot = dot(-L, spotDir);
    
    // Convert cutoff angle to cosine for comparison
    float cutoffCos = cos(spotCutoff * 3.14159265 / 180.0);
    
    // Create a wider soft edge region (20 degrees of smooth falloff)
    float outerCutoff = cos((spotCutoff + 20.0) * 3.14159265 / 180.0);
    
    // Smooth falloff from outer edge to inner cone
    float spotEffect = smoothstep(outerCutoff, cutoffCos, spotDot);
    
    // Apply additional exponential falloff within the cone for smooth gradient
    spotEffect = pow(spotEffect, spotExponent);
    
    // Calculate attenuation
    float attenuation = 1.0 / (constantAtten + linearAtten * distance + quadraticAtten * distance * distance);
    
    // Diffuse lighting
    float diffuse = max(dot(N, L), 0.0);
    vec3 diffuseColor = lightDiffuse * diffuse * baseColor.rgb;
    
    // Specular lighting (Blinn-Phong)
    vec3 V = normalize(-fragPosition);  // View direction
    vec3 H = normalize(L + V);          // Halfway vector
    float specular = pow(max(dot(N, H), 0.0), materialShininess);
    // Apply checkerboard to specular as well
    vec3 specularColor = lightSpecular * materialSpecular * specular;
    if (useCheckerboard) {
        specularColor *= checkerFactor;
    }
    
    // Combine lighting components with spotlight and attenuation
    vec3 finalColor = (diffuseColor + specularColor) * spotEffect * attenuation;
    
    gl_FragColor = vec4(finalColor, baseColor.a);
}
