import os, json, glob, tkinter as tk
from tkinter import ttk, filedialog, messagebox

DEF = r"C:\Games\Borderlands 2 Remastered"
CFG = os.path.join(os.path.expanduser("~"), ".bl2mapeditor.json")
KNOWN = ["Fyrestone_P", "SanctuaryAir_P", "Sanctuary_P", "Boss_Cliffs_P", "Stockade_P", "HyperionCity_P"]
ENEMIES = {"Грузчик": "loader", "Скаг": "skag", "Молотильщик": "thresher", "Стервятник": "buzzard",
           "Булимонг": "bullymong", "Паук-муравей": "spiderant", "Сталкер": "stalker", "Голиаф": "goliath",
           "Псих": "psycho", "Мародёр": "marauder"}

# ---------- рантайм-мод, который редактор кладёт в sdk_mods/MapEdits ----------
RUNTIME = r'''
import json, math, os, random, time, traceback
from mods_base import build_mod, hook, keybind, get_pc, ObjectFlags
import unrealsdk
from unrealsdk import find_all, find_object, logging, make_struct
from unrealsdk.hooks import Type

DIR = os.path.dirname(os.path.abspath(__file__))
DROP = "GD_ConstructorShared.Den.PopPointDef_OrbitalDrop"
FXI = "FX_Fast_Travel.Particles.Fast_Travel_Super_Impact_Part"
PACKS = ["GD_ConstructorShared", "RobotSlaughter_P", "Fyrestone_Combat", "Stockade_Combat"]
st = {"q": [], "t": 0.0, "loaded": False}


def log(*a):
    try:
        logging.info("[MapEdits] " + " ".join(str(x) for x in a))
    except Exception:
        pass


def cfg():
    try:
        return json.load(open(os.path.join(DIR, "edits.json"), encoding="utf-8"))
    except Exception:
        return {}


def factory(key):
    def look():
        r = []
        for f in find_all("PopulationFactoryBalancedAIPawn"):
            p = f.PathName(f).lower()
            if key in p and "unique" not in p:
                r.append(f)
        return r
    r = look()
    if not r and not st["loaded"]:
        st["loaded"] = True
        for pk in PACKS:
            try:
                unrealsdk.load_package(pk)
            except Exception:
                pass
        for cn in ("WillowPopulationDefinition", "PopulationFactoryBalancedAIPawn", "PopulationBodyTag", "BodyClassDefinition"):
            try:
                for o in find_all(cn):
                    o.ObjectFlags |= ObjectFlags.KEEP_ALIVE
            except Exception:
                pass
        r = look()
    return random.choice(r) if r else None


def spawn(e):
    pc = get_pc(); me = pc.Pawn
    if me is None:
        return
    fac = factory(e["enemy"])
    if fac is None:
        log("нет фабрики для", e["enemy"]); return
    loc = me.Location
    p = e.get("pos", "player")
    px, py, pz = (loc.X, loc.Y, loc.Z) if p == "player" else p
    dens = [d for d in find_all("PopulationOpportunityDen") if d.Location]
    if not dens:
        log("нет den"); return
    den = min(dens, key=lambda d: (d.Location.X - px) ** 2 + (d.Location.Y - py) ** 2)
    point, old = None, None
    if e.get("drop"):
        best = 1e18
        for d in dens:
            for sp in d.SpawnPoints:
                if sp and sp.Location:
                    dd = (sp.Location.X - px) ** 2 + (sp.Location.Y - py) ** 2
                    if dd < best and abs(sp.Location.Z - pz) < 600:
                        point, den, best = sp, d, dd
        if point is not None:
            try:
                point.SetLocation(make_struct("Vector", X=px, Y=py, Z=pz))
                old = point.PointDef
                point.PointDef = find_object("WillowPopulationPointDefinition", DROP)
            except Exception:
                log("drop:", traceback.format_exc().splitlines()[-1])
    if point is not None:
        src = point.StretchyActor if getattr(point, "StretchyActor", None) else point
        pos, rot = src.Location, src.Rotation
    else:
        pos, rot = make_struct("Vector", X=px, Y=py, Z=pz + 50), me.Rotation
    pawn = pc.GetWillowGlobals().GetPopulationMaster().SpawnActorFromOpportunity(
        fac, den, pos, rot, me.GetGameStage(), 1, 0, 0, False, False)
    if pawn is None:
        return
    if point is not None:
        try:
            point.ActorSpawned(pawn); pawn.MySpawnPoint = point
            if old is not None:
                point.PointDef = old
        except Exception:
            pass
    try:
        ai = pawn.MyWillowMind.GetAIComponent(); ai.AddTarget(me); ai.NotifyAttackedBy(me)
    except Exception:
        pass


def dmg_for(lv):
    """lv: 1..80 обычные, 81..90 = OP1..OP10. Ур.1 = 80, ур.80 = 2 млн, OP10 = 14 млн."""
    if lv <= 80:
        return 80.0 * (25000.0 ** ((lv - 1) / 79.0))
    return 2000000.0 * (1.0 + 0.6 * (lv - 80))


def bomb(e):
    pc = get_pc(); me = pc.Pawn
    if me is None:
        return
    loc = me.Location
    r = e.get("radius", 20) * 100.0 * math.sqrt(random.random()); a = random.random() * 6.283
    tx, ty = loc.X + r * math.cos(a), loc.Y + r * math.sin(a)
    try:
        ps = find_object("ParticleSystem", FXI)
        pc.WorldInfo.MyEmitterPool.SpawnEmitter(ps, make_struct("Vector", X=tx, Y=ty, Z=loc.Z), me.Rotation, None)
    except Exception:
        pass
    if (tx - loc.X) ** 2 + (ty - loc.Y) ** 2 < 400 ** 2:
        dmg = dmg_for(e["level"]) * random.uniform(0.875, 1.125)
        try:
            me.SetHealth(max(0.0, me.GetHealth() - dmg))
            log("попадание", int(dmg))
        except Exception:
            log("урон:", traceback.format_exc().splitlines()[-1])


def schedule(mapname):
    now = time.monotonic(); st["q"] = []
    for e in cfg().get(mapname, []):
        t = now + e.get("delay", 5)
        for i in range(int(e.get("count", e.get("shots", 1)))):
            st["q"].append((t + i * e.get("interval", 0.5), e))
    log("правок в очереди:", len(st["q"]))


@hook("WillowGame.WillowPlayerController:WillowClientDisableLoadingMovie", Type.POST_UNCONDITIONAL)
def entered(obj, args, ret, func):
    try:
        name = str(get_pc().WorldInfo.GetStreamingPersistentMapName()).lower()
        log("карта", name)
        schedule_map = {k.lower(): k for k in cfg()}
        schedule(schedule_map.get(name, "")) if name in schedule_map else st["q"].clear()
    except Exception:
        log(traceback.format_exc())


def tick_once():
    now = time.monotonic()
    if now - st["t"] < 0.1 or not st["q"]:
        return
    st["t"] = now
    due = [x for x in st["q"] if x[0] <= now]
    st["q"] = [x for x in st["q"] if x[0] > now]
    for _, e in due:
        try:
            spawn(e) if e["kind"] == "spawn" else bomb(e)
        except Exception:
            log(traceback.format_exc())


@keybind("Показать мои координаты", key="F6")
def coords():
    l = get_pc().Pawn.Location
    log("ПОЗИЦИЯ: %.0f, %.0f, %.0f" % (l.X, l.Y, l.Z))


@hook("WillowGame.WillowGameViewportClient:Tick")
def t1(obj, args, ret, func):
    tick_once()


@hook("Engine.GameViewportClient:Tick")
def t2(obj, args, ret, func):
    tick_once()


log("загружен. F6 = мои координаты")
build_mod()
'''


def dmg_for(lv):
    """lv: 1..80 обычные, 81..90 = OP1..OP10. Ур.1 = 80, ур.80 = 2 млн, OP10 = 14 млн."""
    if lv <= 80:
        return 80.0 * (25000.0 ** ((lv - 1) / 79.0))
    return 2000000.0 * (1.0 + 0.6 * (lv - 80))


def parse_level(t):
    t = t.strip().upper()
    n = int(t[2:]) + 80 if t.startswith("OP") else int(t)
    if not 1 <= n <= 90:
        raise ValueError("Уровень: 1-80 или OP1-OP10")
    return n


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BL2 Map Editor")
        self.geometry("900x560")
        try:
            self.cfg = json.load(open(CFG))
        except Exception:
            self.cfg = {}
        self.data = {}
        self.game = tk.StringVar(value=self.cfg.get("game", DEF))
        top = ttk.Frame(self, padding=6); top.pack(fill="x")
        ttk.Label(top, text="Папка игры:").pack(side="left")
        ttk.Entry(top, textvariable=self.game).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(top, text="Обзор", command=self.pick).pack(side="left")
        ttk.Button(top, text="Загрузить карты", command=self.load).pack(side="left", padx=4)
        body = ttk.Frame(self, padding=6); body.pack(fill="both", expand=True)
        left = ttk.Frame(body); left.pack(side="left", fill="y")
        self.flt = tk.StringVar(); self.flt.trace_add("write", lambda *a: self.fill())
        ttk.Entry(left, textvariable=self.flt).pack(fill="x")
        self.lb = tk.Listbox(left, width=26, exportselection=False); self.lb.pack(fill="y", expand=True)
        self.lb.bind("<<ListboxSelect>>", lambda e: self.show())
        mr = ttk.Frame(left); mr.pack(fill="x")
        self.newmap = tk.StringVar(); ttk.Entry(mr, textvariable=self.newmap, width=16).pack(side="left")
        ttk.Button(mr, text="+ карта", command=self.addmap).pack(side="left")
        right = ttk.Frame(body); right.pack(side="left", fill="both", expand=True, padx=8)
        self.tv = ttk.Treeview(right, columns=("t", "d"), show="headings", height=9)
        self.tv.heading("t", text="Тип"); self.tv.heading("d", text="Описание")
        self.tv.column("t", width=110); self.tv.column("d", width=480)
        self.tv.pack(fill="x")
        ttk.Button(right, text="Удалить выбранную правку", command=self.dele).pack(anchor="e")
        f = ttk.LabelFrame(right, text="Новая правка", padding=6); f.pack(fill="x", pady=6)
        self.kind = tk.StringVar(value="Спавн врагов"); self.v = {}
        ttk.Combobox(f, textvariable=self.kind, state="readonly", width=18,
                     values=["Спавн врагов", "Бомбардировка Гелиоса"]).grid(row=0, column=0, columnspan=2, sticky="w")
        spec = [("enemy", "Враг", "Грузчик"), ("count", "Кол-во / выстрелов", "3"), ("level", "Уровень бомб. (1-80 или OP1-OP10)", "80"),
                ("interval", "Интервал, сек", "0.5"), ("delay", "Задержка после входа, сек", "5"),
                ("radius", "Радиус бомб., м", "20"), ("pos", "Точка (player или x,y,z; F6 в игре)", "player")]
        for i, (k, lab, d) in enumerate(spec):
            ttk.Label(f, text=lab).grid(row=i + 1, column=0, sticky="w")
            self.v[k] = tk.StringVar(value=d)
            if k == "enemy":
                ttk.Combobox(f, textvariable=self.v[k], values=list(ENEMIES) + ["(своё ключевое слово)"], width=24).grid(row=i + 1, column=1, sticky="w")
            else:
                ttk.Entry(f, textvariable=self.v[k], width=26).grid(row=i + 1, column=1, sticky="w")
        self.drop = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Сброс с «Гелиоса» (для спавна)", variable=self.drop).grid(row=9, column=0, columnspan=2, sticky="w")
        ttk.Button(f, text="Добавить правку", command=self.add).grid(row=10, column=0, sticky="w", pady=4)
        ttk.Button(right, text="Сохранить и установить в игру", command=self.install).pack(fill="x")
        ttk.Label(right, text="Препятствия, сундуки и квесты пока не поддерживаются (нужна разведка имён объектов).",
                  foreground="#777").pack(anchor="w")
        self.cur = None
        self.maps = []
        self.load()

    def sdkdir(self):
        return os.path.join(self.game.get(), "sdk_mods", "MapEdits")

    def pick(self):
        d = filedialog.askdirectory()
        if d:
            self.game.set(d)

    def load(self):
        g = self.game.get()
        self.cfg["game"] = g; json.dump(self.cfg, open(CFG, "w"))
        found = set()
        for sub in ("WillowGame/CookedPCConsole", "WillowGame/CookedPC"):
            for p in glob.glob(os.path.join(g, *sub.split("/"), "*_P.upk")):
                found.add(os.path.basename(p)[:-4])
        self.maps = sorted(found) or list(KNOWN)
        try:
            self.data = json.load(open(os.path.join(self.sdkdir(), "edits.json"), encoding="utf-8"))
        except Exception:
            self.data = {}
        for m in self.data:
            if m not in self.maps:
                self.maps.append(m)
        self.fill()

    def fill(self):
        self.lb.delete(0, "end")
        q = self.flt.get().lower()
        for m in self.maps:
            if q in m.lower():
                n = len(self.data.get(m, []))
                self.lb.insert("end", m + ("  [%d]" % n if n else ""))

    def sel(self):
        s = self.lb.curselection()
        return self.lb.get(s[0]).split("  [")[0] if s else self.cur

    def addmap(self):
        m = self.newmap.get().strip()
        if m and m not in self.maps:
            self.maps.append(m); self.fill()

    def show(self):
        self.cur = self.sel()
        self.tv.delete(*self.tv.get_children())
        for e in self.data.get(self.cur, []):
            if e["kind"] == "spawn":
                d = "%s ×%d, точка %s%s" % (e["enemy"], e["count"], e["pos"], ", сброс с Гелиоса" if e["drop"] else "")
                t = "Спавн"
            else:
                lv = e["level"]; v = dmg_for(lv)
                d = "ур. %s (~%s урона), выстрелов %d, радиус %d м" % ("OP%d" % (lv - 80) if lv > 80 else lv, format(int(v), ","), e["shots"], e["radius"])
                t = "Бомбардировка"
            self.tv.insert("", "end", values=(t, d))

    def add(self):
        m = self.sel()
        if not m:
            messagebox.showinfo("Карта", "Сначала выберите карту"); return
        try:
            g = lambda k: self.v[k].get().strip()
            p = g("pos")
            pos = "player" if p.lower() == "player" else [float(x) for x in p.replace(";", ",").split(",")][:3]
            if pos != "player" and len(pos) != 3:
                raise ValueError("Точка: player или x,y,z")
            base = {"delay": float(g("delay")), "interval": float(g("interval")), "pos": pos}
            if self.kind.get() == "Спавн врагов":
                en = ENEMIES.get(g("enemy"), g("enemy").lower())
                e = dict(base, kind="spawn", enemy=en, count=int(g("count")), drop=self.drop.get())
            else:
                e = dict(base, kind="bomb", level=parse_level(g("level")), shots=int(g("count")), radius=float(g("radius")))
        except Exception as ex:
            messagebox.showerror("Ошибка", str(ex)); return
        self.data.setdefault(m, []).append(e)
        self.cur = m; self.show(); self.fill()

    def dele(self):
        s = self.tv.selection()
        if s and self.cur:
            del self.data[self.cur][self.tv.index(s[0])]
            self.show(); self.fill()

    def install(self):
        g = self.game.get()
        if not os.path.isdir(g):
            messagebox.showerror("Ошибка", "Нет папки игры"); return
        d = self.sdkdir(); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "__init__.py"), "w", encoding="utf-8").write(RUNTIME)
        json.dump({k: v for k, v in self.data.items() if v}, open(os.path.join(d, "edits.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        messagebox.showinfo("Готово", "Мод установлен в\n" + d + "\nЗапустите игру. F6 = координаты.")


if __name__ == "__main__":
    App().mainloop()
