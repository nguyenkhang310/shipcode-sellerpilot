import { useCallback, useEffect, useLayoutEffect, useRef, type RefObject } from 'react';
import { AppState, Platform, StyleSheet, View } from 'react-native';
import type { ExpoWebGLRenderingContext } from 'expo-gl';
import { LIVE_WAVE_POINTS } from './voiceTurn';

let GLView: typeof import('expo-gl').GLView | undefined;
try { GLView = require('expo-gl').GLView; } catch { /* Older native builds can keep the static control. */ }
let webGLAvailable: boolean | undefined;

function canRender() {
  if (Platform.OS !== 'web') return true;
  if (typeof document === 'undefined') return false;
  if (webGLAvailable !== undefined) return webGLAvailable;
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
    webGLAvailable = Boolean(gl);
    gl?.getExtension('WEBGL_lose_context')?.loseContext();
  } catch { webGLAvailable = false; }
  return webGLAvailable;
}

// An original, procedural light field. The moving surface normal determines
// light and depth at each pixel, so there are no artwork layers to slide around.
const vertex = `
attribute vec2 position;
void main() { gl_Position = vec4(position, 0.0, 1.0); }
`;
const fragment = `
precision mediump float;
uniform vec2 size;
uniform float time;
uniform float energy;
uniform float strength;
uniform float roundFace;
uniform float micLevel;
uniform float micWave[${LIVE_WAVE_POINTS}];

float glow(float distance, float width) {
  float z = distance / width;
  return exp(-z*z);
}

float current(float x, float t) {
  float idle = sin(x*5.2 - t*1.65)*(.034 + .069*energy)
    + sin(x*10.6 + t*2.35)*(.018 + .028*energy);
  if (micLevel < .005) return .51 + idle;
  float index = clamp((x + .5)*${(LIVE_WAVE_POINTS - 1).toFixed(1)}, 0.0, ${(LIVE_WAVE_POINTS - 1).toFixed(1)});
  float wave = 0.0;
  for (int point = 0; point < ${LIVE_WAVE_POINTS}; point++) {
    wave += micWave[point] * (1.0 - smoothstep(0.0, 1.0, abs(index - float(point))));
  }
  float taper = 1.0 - smoothstep(.27, .51, abs(x));
  return .51 + .18*micLevel + idle*(1.0 - .70*micLevel) + wave*.24*taper;
}

void main() {
  vec2 uv = gl_FragCoord.xy / size;
  float x = uv.x - .5;
  float travel = time + .44 * sin(time*.37);
  float y = uv.y;
  float center = current(x, travel);
  float delta = y - center;
  float shape = max(0.0, 1.0 - 3.5*x*x);
  float falloff = pow(shape, 1.6) * (.70 + .30*cos(x*5.0 - travel*.8));
  float thickness = .17 + .10*energy - .077*micLevel;
  float surface = clamp(delta/thickness, -1., 1.);
  float tangent = (current(x+.012, travel) - center) / .012;
  vec3 normal = normalize(vec3(-tangent*.6, surface, sqrt(max(.04, 1.0-surface*surface))));
  float sheen = pow(max(dot(normal, normalize(vec3(-.37,.62,.70))), 0.0), 7.0);

  vec3 color = mix(vec3(.019,.034,.071), vec3(.055,.093,.151), y);
  color += vec3(.11,.19,.39) * glow(delta, thickness*1.22) * falloff * (.28+.37*energy) * strength;
  color += vec3(.12,.41,.73) * glow(delta+.035, thickness*.77) * falloff * (.42+.4*sheen) * strength;
  float heat = pow(max(0.0, cos(x*4.8+travel*.94)),2.0)*falloff;
  color += vec3(.79,.39,.14) * glow(delta-.054, thickness*.39) * heat * (.34+.36*sheen+.24*energy) * strength;
  color += vec3(.35,.55,.68) * glow(delta-.014, thickness*.34) * (sheen*.56 + micLevel*.36) * falloff * strength;
  float top = glow(y-.97,.07) * pow(max(0.0,1.0-3.8*x*x),4.0);
  color += vec3(.33,.42,.54) * top * (.29 + .12*roundFace);
  if (roundFace > .5) {
    vec2 position = uv*2.0 - 1.0;
    float angle = atan(position.y, position.x + .0001);
    float radius = length(position);
    float ring = .61 + sin(angle*3.0-travel*1.7)*(.04+.09*energy);
    float rim = glow(radius-ring,.17)*(.64+.36*sin(angle*2.0+travel));
    vec3 light = mix(vec3(.17,.45,.76),vec3(.82,.39,.13),.5+.5*sin(angle-travel*.8));
    color = mix(vec3(.045,.072,.12)+light*rim*.92, color, .22);
  }
  gl_FragColor = vec4(color, 1.0);
}
`;

function createRenderer(gl: ExpoWebGLRenderingContext) {
  function shader(kind: number, source: string) {
    const handle = gl.createShader(kind);
    if (!handle) return null;
    gl.shaderSource(handle, source);
    gl.compileShader(handle);
    if (gl.getShaderParameter(handle, gl.COMPILE_STATUS)) return handle;
    gl.deleteShader(handle);
    return null;
  }
  const v = shader(gl.VERTEX_SHADER, vertex);
  const f = shader(gl.FRAGMENT_SHADER, fragment);
  const program = gl.createProgram();
  if (!(v && f && program)) {
    if (v) gl.deleteShader(v);
    if (f) gl.deleteShader(f);
    if (program) gl.deleteProgram(program);
    return null;
  }
  gl.attachShader(program, v);
  gl.attachShader(program, f);
  gl.linkProgram(program);
  gl.deleteShader(v); gl.deleteShader(f);
  const buffer = gl.getProgramParameter(program, gl.LINK_STATUS) ? gl.createBuffer() : null;
  if (!buffer) { gl.deleteProgram(program); return null; }
  gl.useProgram(program);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const point = gl.getAttribLocation(program, 'position');
  gl.enableVertexAttribArray(point);
  gl.vertexAttribPointer(point, 2, gl.FLOAT, false, 0, 0);
  const size = gl.getUniformLocation(program, 'size');
  const time = gl.getUniformLocation(program, 'time');
  const energy = gl.getUniformLocation(program, 'energy');
  const strength = gl.getUniformLocation(program, 'strength');
  const roundFace = gl.getUniformLocation(program, 'roundFace');
  const micLevel = gl.getUniformLocation(program, 'micLevel');
  const micWave = gl.getUniformLocation(program, 'micWave[0]');

  return {
    draw(frameTime: number, audioLevel: number, glowAmount: number, round: boolean, inputLevel: number, inputWave: Float32Array) {
      const { drawingBufferWidth: width, drawingBufferHeight: height } = gl;
      if (!width || !height) return;
      gl.viewport(0, 0, width, height);
      gl.uniform2f(size, width, height);
      gl.uniform1f(time, frameTime);
      gl.uniform1f(energy, audioLevel);
      gl.uniform1f(strength, glowAmount);
      gl.uniform1f(roundFace, Number(round));
      gl.uniform1f(micLevel, inputLevel);
      if (inputLevel >= .005) gl.uniform1fv(micWave, inputWave);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.endFrameEXP();
    },
    destroy() { gl.deleteBuffer(buffer); gl.deleteProgram(program); },
  };
}

export function LiveOrb({ round = false, glow = true, animate = false, level, microphone }: {
  round?: boolean;
  glow?: boolean;
  animate?: boolean;
  level?: RefObject<number>;
  microphone?: RefObject<Float32Array>;
}) {
  const renderer = useRef<ReturnType<typeof createRenderer>>(null);
  const params = useRef({ round, glow, animate, level, microphone });
  const frame = useRef(0);
  const aim = useRef(0);
  const wave = useRef(new Float32Array(LIVE_WAVE_POINTS));
  const foreground = useRef(AppState.currentState !== 'background');
  const elapsed = useRef(0);
  const last = useRef(0);
  const update = useCallback(function update(now: number) {
    frame.current = 0;
    if (!renderer.current || !foreground.current) return;
    const config = params.current;
    const input = config.microphone?.current;
    const interval = input?.some(sample => sample !== 0) ? 15 : 1000 / 35;
    if (!config.animate || !last.current || now - last.current >= interval) {
      const delta = Math.min(70, now - (last.current || now));
      last.current = now;
      if (config.animate) elapsed.current += delta / 1000;
      const target = config.level?.current ?? 0;
      aim.current += (target - aim.current) * (target > aim.current ? .42 : .16);
      let inputLevel = 0;
      if (input && config.animate) {
        let peak = 0;
        for (let index = 0; index < LIVE_WAVE_POINTS; index++) {
          const previous = wave.current[index] ?? 0;
          const value = previous + ((input[index] ?? 0) - previous) * .55;
          wave.current[index] = value;
          peak = Math.max(peak, Math.abs(value));
        }
        inputLevel = Math.min(1, peak * 2.4);
      } else {
        wave.current.fill(0);
      }
      renderer.current.draw(elapsed.current % 100, config.animate ? aim.current : 0,
        config.glow ? 1 : .35, config.round, inputLevel, wave.current);
    }
    if (config.animate) frame.current = requestAnimationFrame(update);
  }, []);
  const refresh = useCallback(() => {
    if (frame.current) cancelAnimationFrame(frame.current);
    last.current = 0;
    frame.current = requestAnimationFrame(update);
  }, [update]);
  useLayoutEffect(() => {
    params.current = { round, glow, animate, level, microphone };
    refresh();
  }, [round, glow, animate, level, microphone, refresh]);
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => {
      foreground.current = state === 'active';
      refresh();
    });
    return () => {
      subscription.remove();
      if (frame.current) cancelAnimationFrame(frame.current);
      renderer.current?.destroy();
      renderer.current = null;
    };
  }, [refresh]);

  return <View pointerEvents="none" accessible={false} accessibilityElementsHidden
    importantForAccessibility="no-hide-descendants" style={[StyleSheet.absoluteFill, styles.surface, round && styles.round]}>
    {GLView && canRender() ? <GLView style={StyleSheet.absoluteFill} msaaSamples={0} onLayout={refresh} onContextCreate={gl => {
      try {
        renderer.current?.destroy();
        renderer.current = createRenderer(gl);
        refresh();
      } catch {
        renderer.current = null;
      }
    }} /> : null}
  </View>;
}

const styles = StyleSheet.create({
  surface: { borderRadius: 24, overflow: 'hidden', backgroundColor: '#0C1526' },
  round: { borderRadius: 999 },
});
