#version 120
varying vec3 fragNormal;
varying vec3 fragPosition;
varying vec3 fragWorldPosition;
varying vec2 fragTexCoord;
varying vec4 fragColor;
varying vec3 fragTangent;
varying vec3 fragBitangent;

uniform sampler2D textureSampler;
uniform bool useTexture;
uniform bool useCheckerboard;
uniform float checkerboardScale;

// Light properties
uniform vec3 lightPosition;
uniform vec3 lightDirection;
uniform float spotCutoff;
uniform float spotExponent;
uniform vec3 lightColor;
uniform float lightIntensity;

// Material properties (PBR-like)
uniform vec3 baseColor;
uniform float metallic;
uniform float roughness;
uniform float ao;  // Ambient occlusion

const float PI = 3.14159265359;
const float AMBIENT_LIGHT = 0.0;  // Ambient lighting constant

// ===== MATERIAL FUNCTIONS =====
vec3 getMaterialBaseColor() {
    vec4 texColor;
    if (useTexture) {
        texColor = texture2D(textureSampler, fragTexCoord);
    } else {
        texColor = fragColor;
    }
    
    // Apply checkerboard pattern if enabled
    if (useCheckerboard) {
        float checkX = floor(fragWorldPosition.x / checkerboardScale);
        float checkZ = floor(fragWorldPosition.z / checkerboardScale);
        float pattern = mod(checkX + checkZ, 2.0);
        float checkerFactor = mix(0.3, 0.7, pattern);
        texColor.rgb *= checkerFactor;
    }
    
    return texColor.rgb * baseColor;
}

float getMaterialAlpha() {
    if (useTexture) {
        return texture2D(textureSampler, fragTexCoord).a;
    }
    return fragColor.a;
}

// ===== PBR LIGHTING FUNCTIONS =====

// Normal Distribution Function (GGX/Trowbridge-Reitz)
float distributionGGX(vec3 N, vec3 H, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float NdotH = max(dot(N, H), 0.0);
    float NdotH2 = NdotH * NdotH;
    
    float nom = a2;
    float denom = (NdotH2 * (a2 - 1.0) + 1.0);
    denom = PI * denom * denom;
    
    return nom / denom;
}

// Geometry Function (Schlick-GGX)
float geometrySchlickGGX(float NdotV, float roughness) {
    float r = (roughness + 1.0);
    float k = (r * r) / 8.0;
    
    float nom = NdotV;
    float denom = NdotV * (1.0 - k) + k;
    
    return nom / denom;
}

float geometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
    float NdotV = max(dot(N, V), 0.0);
    float NdotL = max(dot(N, L), 0.0);
    float ggx2 = geometrySchlickGGX(NdotV, roughness);
    float ggx1 = geometrySchlickGGX(NdotL, roughness);
    
    return ggx1 * ggx2;
}

// Fresnel-Schlick approximation
vec3 fresnelSchlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(1.0 - cosTheta, 5.0);
}

// Calculate PBR lighting
vec3 calculatePBRLighting(vec3 N, vec3 V, vec3 L, vec3 albedo, float metallic, float roughness, vec3 F0, vec3 radiance) {
    vec3 H = normalize(V + L);
    
    // Cook-Torrance BRDF
    float NDF = distributionGGX(N, H, roughness);
    float G = geometrySmith(N, V, L, roughness);
    vec3 F = fresnelSchlick(max(dot(H, V), 0.0), F0);
    
    vec3 numerator = NDF * G * F;
    float denominator = 4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0) + 0.0001;
    vec3 specular = numerator / denominator;
    
    // Energy conservation
    vec3 kS = F;
    vec3 kD = vec3(1.0) - kS;
    kD *= 1.0 - metallic;
    
    float NdotL = max(dot(N, L), 0.0);
    return (kD * albedo / PI + specular) * radiance * NdotL;
}

// ===== LIGHT ATTENUATION FUNCTIONS =====

// Spotlight effect with smooth falloff
float calculateSpotlightEffect(vec3 L, vec3 spotDir, float cutoffAngle, float exponent) {
    float spotDot = dot(-L, spotDir);
    float cutoffCos = cos(cutoffAngle * PI / 180.0);
    float outerCutoff = cos((cutoffAngle + 20.0) * PI / 180.0);
    
    float spotEffect = smoothstep(outerCutoff, cutoffCos, spotDot);
    return pow(spotEffect, exponent);
}

// Distance attenuation (inverse square law with adjustments)
float calculateAttenuation(float distance) {
    // Physical inverse square falloff with small constant to prevent singularity
    return 1.0 / (1.0 + 0.09 * distance + 0.032 * distance * distance);
}

void main() {
    // Get material properties
    vec3 albedo = getMaterialBaseColor();
    float alpha = getMaterialAlpha();
    
    // Setup surface properties
    vec3 N = normalize(fragNormal);
    vec3 V = normalize(-fragPosition);
    
    // Calculate light vector
    vec3 L = lightPosition - fragPosition;
    float distance = length(L);
    L = normalize(L);
    
    // Calculate Fresnel reflectance at normal incidence
    vec3 F0 = vec3(0.04);  // Base reflectance for dielectrics
    F0 = mix(F0, albedo, metallic);
    
    // Calculate spotlight effect
    vec3 spotDir = normalize(lightDirection);
    float spotEffect = calculateSpotlightEffect(L, spotDir, spotCutoff, spotExponent);
    
    // Calculate attenuation
    float attenuation = calculateAttenuation(distance);
    
    // Calculate radiance
    vec3 radiance = lightColor * lightIntensity * attenuation * spotEffect;
    
    // Calculate PBR lighting
    vec3 Lo = calculatePBRLighting(N, V, L, albedo, metallic, roughness, F0, radiance);
    
    // Apply ambient lighting (currently set to 0)
    vec3 ambient = AMBIENT_LIGHT * albedo * ao;
    vec3 color = ambient + Lo;
    
    // HDR tone mapping (simple Reinhard)
    color = color / (color + vec3(1.0));
    
    // Gamma correction (approximate)
    color = pow(color, vec3(1.0 / 2.2));
    
    gl_FragColor = vec4(color, alpha);
}
