// Offscreen GLES3 throughput test, runs from /data/local/tmp inside the guest (no UI, no APK).
// Renders FRAMES full-screen passes of a heavy fragment shader into a W x H FBO, glFinish() each frame,
// then reads one pixel row back so the work cannot be skipped. Prints one line of key=value results.
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000.0 + t.tv_nsec / 1e6;
}

static GLuint compile(GLenum type, const char *src) {
    GLuint s = glCreateShader(type);
    glShaderSource(s, 1, &src, NULL);
    glCompileShader(s);
    GLint ok = 0;
    glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[1024];
        glGetShaderInfoLog(s, sizeof log, NULL, log);
        fprintf(stderr, "shader error: %s\n", log);
        exit(2);
    }
    return s;
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    int W = argc > 1 ? atoi(argv[1]) : 1280;
    int H = argc > 2 ? atoi(argv[2]) : 720;
    int FRAMES = argc > 3 ? atoi(argv[3]) : 120;
    int ITER = argc > 4 ? atoi(argv[4]) : 64;  // shader loop count: scales the per-pixel work

    EGLDisplay dpy = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if (!eglInitialize(dpy, NULL, NULL)) { fprintf(stderr, "eglInitialize failed\n"); return 3; }
    const EGLint cfg_attr[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
                               EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
    EGLConfig cfg;
    EGLint n = 0;
    if (!eglChooseConfig(dpy, cfg_attr, &cfg, 1, &n) || n < 1) { fprintf(stderr, "no config\n"); return 3; }
    const EGLint pb[] = {EGL_WIDTH, 16, EGL_HEIGHT, 16, EGL_NONE};
    EGLSurface surf = eglCreatePbufferSurface(dpy, cfg, pb);
    const EGLint ctx_attr[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
    EGLContext ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, ctx_attr);
    if (ctx == EGL_NO_CONTEXT || !eglMakeCurrent(dpy, surf, surf, ctx)) { fprintf(stderr, "context failed\n"); return 3; }

    GLuint tex, fbo;
    glGenTextures(1, &tex);
    glBindTexture(GL_TEXTURE_2D, tex);
    glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, W, H);
    glGenFramebuffers(1, &fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) { fprintf(stderr, "fbo incomplete\n"); return 3; }
    glViewport(0, 0, W, H);

    const char *vs = "#version 300 es\nout vec2 uv;\nvoid main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);"
                     "uv=p;gl_Position=vec4(p*2.0-1.0,0.0,1.0);}\n";
    char fs[1024];
    snprintf(fs, sizeof fs,
             "#version 300 es\nprecision highp float;\nin vec2 uv;\nuniform float t;\nout vec4 o;\n"
             "void main(){vec2 c=(uv-0.5)*3.0;vec2 z=c;float k=0.0;\n"
             "for(int i=0;i<%d;i++){z=vec2(z.x*z.x-z.y*z.y,2.0*z.x*z.y)+c+0.05*vec2(sin(t),cos(t));"
             "k+=exp(-dot(z,z)*0.1);}\n"
             "o=vec4(fract(k*0.1),fract(k*0.05),fract(k*0.02),1.0);}\n", ITER);
    GLuint prog = glCreateProgram();
    glAttachShader(prog, compile(GL_VERTEX_SHADER, vs));
    glAttachShader(prog, compile(GL_FRAGMENT_SHADER, fs));
    glLinkProgram(prog);
    glUseProgram(prog);
    GLint tloc = glGetUniformLocation(prog, "t");
    GLuint vao;
    glGenVertexArrays(1, &vao);
    glBindVertexArray(vao);

    for (int i = 0; i < 3; i++) { glUniform1f(tloc, i); glDrawArrays(GL_TRIANGLES, 0, 3); }  // warm-up
    glFinish();
    double t0 = now_ms(), worst = 0, prev = t0;
    for (int i = 0; i < FRAMES; i++) {
        glUniform1f(tloc, 0.01f * i);
        glDrawArrays(GL_TRIANGLES, 0, 3);
        glFinish();
        double t = now_ms();
        if (t - prev > worst) worst = t - prev;
        prev = t;
    }
    double total = now_ms() - t0;
    unsigned char row[4 * 64];
    glReadPixels(W / 2, H / 2, 16, 1, GL_RGBA, GL_UNSIGNED_BYTE, row);
    unsigned sum = 0;
    for (int i = 0; i < 64; i++) sum += row[i];

    printf("renderer=\"%s\" size=%dx%d frames=%d iter=%d total_ms=%.1f avg_ms=%.2f fps=%.1f worst_ms=%.1f checksum=%u\n",
           (const char *)glGetString(GL_RENDERER), W, H, FRAMES, ITER, total, total / FRAMES, FRAMES * 1000.0 / total,
           worst, sum);
    fflush(stdout);
    _exit(0);  // skip driver teardown: the gfxstream EGL stack can abort in static destructors at exit
}
