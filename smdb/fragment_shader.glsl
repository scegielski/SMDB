#version 120
varying vec3 fragNormal;
varying vec3 fragPosition;
varying vec3 fragWorldPosition;
varying vec2 fragTexCoord;
varying vec4 fragColor;
varying vec3 fragTangent;
varying vec3 fragBitangent;
varying vec4 fragShadowCoord;

uniform sampler2D textureSampler;
uniform sampler2D shadowMap;
uniform bool useTexture;
uniform bool useCheckerboard;
uniform float checkerboardScale;
uniform bool useShadows;
uniform float shadowBias;
uniform float shadowDarkness;
uniform float shadowMapSize;

// Light properties
uniform vec3 lightPosition;
uniform vec3 lightDirection;
uniform float spotCutoff;
uniform float spotInnerAngle;  // Inner cone angle (full intensity)
uniform float spotCenterBoost;    // Center brightness boost
uniform vec3 lightColor;
uniform vec3 lightCenterColor;    // Light color at center of cone
uniform vec3 lightEdgeColor;      // Light color at edge of cone
uniform float lightColorBlendExp; // Exponent for color blending curve
uniform float lightColorBlendStart; // Radial position where blend starts (0=edge, 1=center)
uniform float lightColorBlendEnd;   // Radial position where blend ends (0=edge, 1=center)
uniform float lightIntensity;
uniform float attenuationLinear;
uniform float attenuationQuadratic;
uniform float ambientLight;  // Ambient lighting constant

// Material properties (PBR-like)
uniform vec3 baseColor;
uniform vec3 groundBaseColor;
uniform float metallic;
uniform float roughness;
uniform float ao;  // Ambient occlusion

const float PI = 3.14159265359;

// ===== MATERIAL FUNCTIONS =====
vec3 getMaterialBaseColor() {
    vec4 texColor;
    if (useTexture) {
        texColor = texture2D(textureSampler, fragTexCoord);
        
        // Composite white text over box color based on texture alpha
        // If texture is fully transparent (alpha = 0), show box color
        // If texture is fully opaque (alpha = 1), show white text
        // fragColor contains the BOX_COLOR for back face
        texColor.rgb = mix(fragColor.rgb, texColor.rgb, texColor.a);
    } else {
        texColor = fragColor;
    }
    
    // Apply checkerboard pattern if enabled
    if (useCheckerboard) {
        float checkX = floor(fragWorldPosition.x / checkerboardScale);
        float checkZ = floor(fragWorldPosition.z / checkerboardScale);
        float pattern = mod(checkX + checkZ, 2.0);
        float checkerFactor = mix(0.6, 0.9, pattern);
        texColor.rgb *= checkerFactor;
        return texColor.rgb * groundBaseColor;
    }
    
    return texColor.rgb * baseColor;
}

float getMaterialAlpha() {
    // Always return 1.0 for opaque rendering after compositing
    return 1.0;
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
// Returns both intensity and radial position (for color blending)
void calculateSpotlightEffect(vec3 L, vec3 spotDir, float outerAngle, float innerAngle, 
                               out float intensity, out float radialPos) {
    // If cone angle is 0 or negative, no spotlight effect
    if (outerAngle <= 0.0) {
        intensity = 0.0;
        radialPos = 0.0;
        return;
    }
    
    // Calculate angle between light direction and spotlight direction
    float spotDot = dot(-L, spotDir);
    
    // Convert angles from degrees to cosine
    // Note: smaller angles → larger cosine values (cos is decreasing function)
    float outerCutoffCos = cos(outerAngle * PI / 180.0);
    
    // Clamp inner angle to be within outer angle
    float clampedInnerAngle = min(innerAngle, outerAngle);
    float innerCutoffCos = cos(clampedInnerAngle * PI / 180.0);
    
    // Smooth transition between inner (full intensity) and outer (zero intensity)
    // When innerAngle == outerAngle: hard edge (no transition)
    // When innerAngle < outerAngle: smooth gradient between the two
    intensity = smoothstep(outerCutoffCos, innerCutoffCos, spotDot);
    
    // Calculate radial position from center to edge of cone (0 = edge, 1 = center)
    // Use outer cutoff for consistent positioning
    float normalizedDot = (spotDot - outerCutoffCos) / max(1.0 - outerCutoffCos, 0.0001);
    radialPos = clamp(normalizedDot, 0.0, 1.0);
    
    // Apply center boost to make the very center even brighter
    float radialFactor = 1.0;
    if (spotCenterBoost > 1.0) {
        // Boost the brightest part (center) even more
        float centerFactor = pow(radialPos, 4.0);  // Sharp center detection
        radialFactor = mix(1.0, spotCenterBoost, centerFactor);
    }
    
    intensity *= radialFactor;
}

// Distance attenuation (inverse square law with adjustments)
float calculateAttenuation(float distance) {
    // Configurable attenuation: lower coefficients = softer falloff
    // Set both to 0 for no distance attenuation (constant intensity)
    return 1.0 / (1.0 + attenuationLinear * distance + attenuationQuadratic * distance * distance);
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
    
    // Calculate spotlight effect and radial position
    vec3 spotDir = normalize(lightDirection);
    float spotEffect;
    float radialPosition;
    calculateSpotlightEffect(L, spotDir, spotCutoff, spotInnerAngle, spotEffect, radialPosition);
    
    // Remap radial position based on start and end blend angles
    // radialPosition goes from 0 (edge) to 1 (center)
    // Remap to blend range: anything before start = edge color, after end = center color
    float blendStart = clamp(lightColorBlendStart, 0.0, 1.0);
    float blendEnd = clamp(lightColorBlendEnd, 0.0, 1.0);
    float colorBlendFactor = 0.0;
    
    if (blendEnd > blendStart) {
        // Normal case: blend from start to end
        colorBlendFactor = clamp((radialPosition - blendStart) / (blendEnd - blendStart), 0.0, 1.0);
    } else {
        // Reversed or same: just use radialPosition
        colorBlendFactor = radialPosition;
    }
    
    // Apply exponent to color blend factor
    if (lightColorBlendExp > 0.0) {
        colorBlendFactor = pow(colorBlendFactor, lightColorBlendExp);
    }
    
    // Blend between edge color and center color
    vec3 spotColor = mix(lightEdgeColor, lightCenterColor, colorBlendFactor);
    
    // Calculate attenuation
    float attenuation = calculateAttenuation(distance);
    
    // Calculate shadow factor
    float shadow = 1.0;
    if (useShadows) {
        // Check if shadow coordinate is valid
        if (fragShadowCoord.w > 0.0) {
            // Perspective divide
            vec3 projCoords = fragShadowCoord.xyz / fragShadowCoord.w;
            
            // Check if coordinates are in valid range (skip Z check - it's for depth compare only)
            bool inShadowMapBounds = (projCoords.x >= 0.0 && projCoords.x <= 1.0 && 
                                      projCoords.y >= 0.0 && projCoords.y <= 1.0);
            
            // Only apply shadows if within shadow map bounds
            if (inShadowMapBounds) {
                
                // Sample shadow map with PCF (Percentage Closer Filtering) for soft shadows
                float shadowSum = 0.0;
                float texelSize = 1.0 / shadowMapSize;
                int pcfSamples = 0;
                
                // 3x3 PCF kernel with manual depth comparison
                for (int x = -1; x <= 1; x++) {
                    for (int y = -1; y <= 1; y++) {
                        vec2 offset = vec2(float(x), float(y)) * texelSize;
                        float shadowDepth = texture2D(shadowMap, projCoords.xy + offset).r;
                        // Use absolute Z since it might be negative depending on projection
                        float currentDepth = abs(projCoords.z) - shadowBias;
                        shadowSum += (currentDepth <= shadowDepth) ? 1.0 : 0.0;
                        pcfSamples++;
                    }
                }
                
                shadow = shadowSum / float(pcfSamples);
                // Apply shadow darkness
                shadow = mix(1.0 - shadowDarkness, 1.0, shadow);
            } else {
                // Outside shadow map bounds - no shadow
                shadow = 1.0;
            }
        } else {
            // Invalid w coordinate - no shadow
            shadow = 1.0;
        }
    }
    
    // Calculate radiance using blended color and shadow
    vec3 radiance = spotColor * lightIntensity * attenuation * spotEffect * shadow;
    
    // Calculate PBR lighting
    vec3 Lo = calculatePBRLighting(N, V, L, albedo, metallic, roughness, F0, radiance);
    
    // Apply ambient lighting
    vec3 ambient = ambientLight * albedo * ao;
    vec3 color = ambient + Lo;
    
    // HDR tone mapping (gentler Reinhard to preserve saturation)
    //color = color / (color + vec3(0.5));
    
    // Gamma correction (approximate)
    //color = pow(color, vec3(1.0 / 2.2));
    
    gl_FragColor = vec4(color, alpha);
}
