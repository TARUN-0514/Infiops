//! NEXUS for Windows: the NEXUS web app in its own window, a tray icon, a global
//! push-to-talk shortcut (Ctrl+Shift+Space), desktop notifications, and the local agent
//! (`nexus-agent run`) started and stopped with the app. Release builds update themselves
//! from signed GitHub releases when you choose to (see `updates.rs`).

mod updates;

use std::net::{TcpStream, ToSocketAddrs};
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;

use serde::Deserialize;
use tauri::menu::{IsMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder, WindowEvent, Wry};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

const PUSH_TO_TALK_EVENT: &str = "nexus://push-to-talk";

#[derive(Deserialize, Clone)]
#[serde(default)]
struct DesktopConfig {
    /// Where the NEXUS web app runs.
    url: String,
    /// Start the local agent with the app and stop it on quit.
    start_agent: bool,
    agent_command: Vec<String>,
}

impl Default for DesktopConfig {
    fn default() -> Self {
        Self {
            url: "http://localhost:3000".into(),
            start_agent: true,
            agent_command: vec!["nexus-agent".into(), "run".into()],
        }
    }
}

fn config_path() -> PathBuf {
    let base = std::env::var_os("APPDATA")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".config")))
        .unwrap_or_default();
    base.join("NEXUS").join("desktop.json")
}

fn load_config() -> DesktopConfig {
    let mut cfg: DesktopConfig = std::fs::read_to_string(config_path())
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default();
    if let Ok(url) = std::env::var("NEXUS_URL") {
        cfg.url = url;
    }
    cfg
}

/// True when something is listening at the URL's host and port.
fn reachable(url: &url::Url) -> bool {
    let (Some(host), Some(port)) = (url.host_str(), url.port_or_known_default()) else {
        return false;
    };
    (host, port)
        .to_socket_addrs()
        .ok()
        .and_then(|mut addrs| addrs.next())
        .map(|addr| TcpStream::connect_timeout(&addr, Duration::from_millis(800)).is_ok())
        .unwrap_or(false)
}

struct AgentProcess(Mutex<Option<Child>>);

fn start_agent(cfg: &DesktopConfig) -> Option<Child> {
    let (program, args) = cfg.agent_command.split_first()?;
    let mut cmd = Command::new(program);
    cmd.args(args);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    match cmd.spawn() {
        Ok(child) => Some(child),
        Err(err) => {
            eprintln!("could not start the local agent ({program}): {err}");
            None
        }
    }
}

pub(crate) fn stop_agent(app: &AppHandle) {
    if let Some(state) = app.try_state::<AgentProcess>() {
        if let Some(mut child) = state.0.lock().expect("agent lock").take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn agent_running(app: &AppHandle) -> bool {
    app.try_state::<AgentProcess>()
        .map(|s| {
            let mut guard = s.0.lock().expect("agent lock");
            match guard.as_mut().map(|c| c.try_wait()) {
                Some(Ok(None)) => true,
                Some(_) => {
                    *guard = None;
                    false
                }
                None => false,
            }
        })
        .unwrap_or(false)
}

fn show_main(app: &AppHandle) {
    let cfg = load_config();
    if let Some(window) = app.get_webview_window("main") {
        // Reload the app if it was offline when the window opened.
        if let Ok(url) = url::Url::parse(&cfg.url) {
            let on_fallback = window.url().map(|u| u.scheme() == "tauri").unwrap_or(false);
            if on_fallback && reachable(&url) {
                let _ = window.navigate(url);
            }
        }
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn push_to_talk(app: &AppHandle) {
    show_main(app);
    let _ = app.emit(PUSH_TO_TALK_EVENT, ());
}

fn build_window(app: &AppHandle, cfg: &DesktopConfig) -> tauri::Result<()> {
    let target = url::Url::parse(&cfg.url)
        .ok()
        .filter(reachable)
        .map(WebviewUrl::External)
        .unwrap_or_else(|| WebviewUrl::App("index.html".into()));
    let window = WebviewWindowBuilder::new(app, "main", target)
        .title("NEXUS")
        .inner_size(1280.0, 840.0)
        .min_inner_size(380.0, 560.0)
        .build()?;
    let handle = app.clone();
    window.on_window_event(move |event| {
        // Closing the window keeps NEXUS in the tray; Quit is in the tray menu.
        if let WindowEvent::CloseRequested { api, .. } = event {
            api.prevent_close();
            if let Some(w) = handle.get_webview_window("main") {
                let _ = w.hide();
            }
        }
    });
    Ok(())
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Open NEXUS", true, None::<&str>)?;
    let talk = MenuItem::with_id(
        app,
        "talk",
        "Push to talk  (Ctrl+Shift+Space)",
        true,
        None::<&str>,
    )?;
    let agent_label = if agent_running(app) {
        "Stop local agent"
    } else {
        "Start local agent"
    };
    let agent = MenuItem::with_id(app, "agent", agent_label, true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit NEXUS", true, None::<&str>)?;
    let version = MenuItem::with_id(
        app,
        "version",
        format!("NEXUS {}", app.package_info().version),
        false,
        None::<&str>,
    )?;
    let sep = PredefinedMenuItem::separator(app)?;
    let update = if updates::enabled(app.config()) {
        Some(updates::menu_item(app)?)
    } else {
        None
    };
    let mut items: Vec<&dyn IsMenuItem<Wry>> = vec![&open, &talk, &sep, &agent, &sep, &version];
    if let Some(item) = update.as_ref() {
        items.push(item);
    }
    items.extend([&sep as &dyn IsMenuItem<Wry>, &quit]);
    let menu = Menu::with_items(app, &items)?;
    let agent_item = agent.clone();
    let mut tray = TrayIconBuilder::with_id("nexus")
        .tooltip(format!("NEXUS {}", app.package_info().version))
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, event| match event.id.as_ref() {
            "open" => show_main(app),
            "talk" => push_to_talk(app),
            "agent" => {
                if agent_running(app) {
                    stop_agent(app);
                    let _ = agent_item.set_text("Start local agent");
                } else if let Some(child) = start_agent(&load_config()) {
                    if let Some(state) = app.try_state::<AgentProcess>() {
                        *state.0.lock().expect("agent lock") = Some(child);
                    }
                    let _ = agent_item.set_text("Stop local agent");
                }
            }
            updates::MENU_ID => {
                let app = app.clone();
                tauri::async_runtime::spawn(async move { updates::on_menu(&app).await });
            }
            "quit" => {
                stop_agent(app);
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let tauri::tray::TrayIconEvent::Click {
                button: tauri::tray::MouseButton::Left,
                button_state: tauri::tray::MouseButtonState::Up,
                ..
            } = event
            {
                show_main(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone());
    }
    tray.build(app)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let ptt = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::Space);
    let context = tauri::generate_context!();
    let with_updater = updates::enabled(context.config());
    let mut builder = tauri::Builder::default();
    if with_updater {
        builder = builder.plugin(tauri_plugin_updater::Builder::new().build());
    }
    builder
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main(app)
        }))
        .plugin(tauri_plugin_notification::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    if shortcut == &ptt && event.state() == ShortcutState::Pressed {
                        push_to_talk(app);
                    }
                })
                .build(),
        )
        .setup(move |app| {
            let cfg = load_config();
            let child = if cfg.start_agent {
                start_agent(&cfg)
            } else {
                None
            };
            app.manage(AgentProcess(Mutex::new(child)));
            build_window(app.handle(), &cfg)?;
            build_tray(app.handle())?;
            if let Err(err) = app.global_shortcut().register(ptt) {
                eprintln!("push-to-talk shortcut unavailable: {err}");
            }
            if with_updater {
                updates::start_background_checks(app.handle().clone());
            }
            Ok(())
        })
        .build(context)
        .expect("error while building NEXUS")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                stop_agent(app);
            }
        });
}
