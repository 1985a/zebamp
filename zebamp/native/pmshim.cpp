// Tiny C ABI over libprojectM 3.x (C++ API) so Zebamp can drive it via ctypes.
#include <libprojectM/projectM.hpp>
#include <cstring>
#include <exception>
#include <string>

namespace {
std::string g_error;
struct PM {
    projectM *pm;
    std::string name;
};
}

extern "C" {

void *zpm_create(const char *presets, const char *datadir, int w, int h, int fps,
                 int mesh_x, int mesh_y, int tex, int duration, int smooth, int shuffle,
                 int hardcut, int hardcut_duration, float hardcut_sens, float beat_sens, int aspect) {
    try {
        projectM::Settings s;
        s.meshX = mesh_x;
        s.meshY = mesh_y;
        s.fps = fps;
        s.textureSize = tex;
        s.windowWidth = w;
        s.windowHeight = h;
        s.presetURL = presets;
        s.datadir = datadir;
        s.titleFontURL = std::string(datadir) + "/fonts/Vera.ttf";
        s.menuFontURL = std::string(datadir) + "/fonts/VeraMono.ttf";
        s.presetDuration = duration;
        s.smoothPresetDuration = smooth;
        s.hardcutEnabled = hardcut != 0;
        s.hardcutDuration = hardcut_duration;
        s.hardcutSensitivity = hardcut_sens;
        s.beatSensitivity = beat_sens;
        s.aspectCorrection = aspect != 0;
        s.easterEgg = 1.0f;
        s.shuffleEnabled = shuffle != 0;
        s.softCutRatingsEnabled = false;
        PM *p = new PM;
        p->pm = new projectM(s, 0);
        return p;
    } catch (const std::exception &e) {
        g_error = e.what();
        return nullptr;
    } catch (...) {
        g_error = "unknown error";
        return nullptr;
    }
}

const char *zpm_error() { return g_error.c_str(); }

void zpm_destroy(void *h) {
    PM *p = static_cast<PM *>(h);
    if (!p) return;
    delete p->pm;
    delete p;
}

void zpm_resize(void *h, int w, int hh) { static_cast<PM *>(h)->pm->projectM_resetGL(w, hh); }
void zpm_render(void *h) { static_cast<PM *>(h)->pm->renderFrame(); }

void zpm_pcm_float(void *h, const float *data, int n) {
    static_cast<PM *>(h)->pm->pcm()->addPCMfloat(data, n);
}

void zpm_next(void *h, int hard) { static_cast<PM *>(h)->pm->selectNext(hard != 0); }
void zpm_prev(void *h, int hard) { static_cast<PM *>(h)->pm->selectPrevious(hard != 0); }
void zpm_random(void *h, int hard) { static_cast<PM *>(h)->pm->selectRandom(hard != 0); }
void zpm_lock(void *h, int on) { static_cast<PM *>(h)->pm->setPresetLock(on != 0); }
int zpm_locked(void *h) { return static_cast<PM *>(h)->pm->isPresetLocked() ? 1 : 0; }
void zpm_shuffle(void *h, int on) { static_cast<PM *>(h)->pm->setShuffleEnabled(on != 0); }
unsigned zpm_count(void *h) { return static_cast<PM *>(h)->pm->getPlaylistSize(); }

int zpm_index(void *h) {
    unsigned i = 0;
    return static_cast<PM *>(h)->pm->selectedPresetIndex(i) ? (int)i : -1;
}

const char *zpm_name(void *h, unsigned i) {
    PM *p = static_cast<PM *>(h);
    if (i >= p->pm->getPlaylistSize()) return "";
    p->name = p->pm->getPresetName(i);
    return p->name.c_str();
}

void zpm_select(void *h, unsigned i, int hard) { static_cast<PM *>(h)->pm->selectPreset(i, hard != 0); }
void zpm_title(void *h, const char *t) { static_cast<PM *>(h)->pm->projectM_setTitle(t ? t : ""); }
void zpm_duration(void *h, int sec) { static_cast<PM *>(h)->pm->changePresetDuration(sec); }
void zpm_toast(void *h, const char *t) { static_cast<PM *>(h)->pm->setToastMessage(t ? t : ""); }
void zpm_key(void *h, int ev, int key, int mod) {
    static_cast<PM *>(h)->pm->key_handler((projectMEvent)ev, (projectMKeycode)key, (projectMModifier)mod);
}

}
