//! Auto-update from signed GitHub releases.
//!
//! The updater is on only in release builds made by `.github/workflows/desktop-release.yml`,
//! which adds the update endpoint and the public key to the config. A local `pnpm build`
//! has no key, so it never checks. Updates are never installed silently: NEXUS checks at
//! start and every six hours, shows a notification, and installs only when you choose
//! "Install update" in the tray. Each download's signature is checked against the public
//! key built into the app, including the version it was signed for, so an older release
//! can't be passed off as a newer one.

use std::sync::Mutex;
use std::time::Duration;

use tauri::menu::MenuItem;
use tauri::{AppHandle, Manager, Wry};
use tauri_plugin_notification::NotificationExt;
use tauri_plugin_updater::{Update, UpdaterExt};

const CHECK_EVERY: Duration = Duration::from_secs(6 * 60 * 60);
pub const MENU_ID: &str = "update";
const CHECK_LABEL: &str = "Check for updates";

/// An update that was found and not yet installed, and the last version we told the owner
/// about (so the notification isn't repeated every six hours).
#[derive(Default)]
pub struct Pending {
    update: Mutex<Option<Update>>,
    announced: Mutex<Option<String>>,
}

pub struct UpdateMenu(pub MenuItem<Wry>);

/// True when this build was made with an update key and endpoint.
pub fn enabled(config: &tauri::Config) -> bool {
    config.plugins.0.contains_key("updater")
}

pub fn menu_item(app: &AppHandle) -> tauri::Result<MenuItem<Wry>> {
    let item = MenuItem::with_id(app, MENU_ID, CHECK_LABEL, true, None::<&str>)?;
    app.manage(UpdateMenu(item.clone()));
    app.manage(Pending::default());
    Ok(item)
}

fn set_menu(app: &AppHandle, label: &str, enabled: bool) {
    if let Some(menu) = app.try_state::<UpdateMenu>() {
        let _ = menu.0.set_text(label);
        let _ = menu.0.set_enabled(enabled);
    }
}

fn notify(app: &AppHandle, title: &str, body: &str) {
    let _ = app.notification().builder().title(title).body(body).show();
}

/// Check now and every six hours, on a background thread.
pub fn start_background_checks(app: AppHandle) {
    std::thread::spawn(move || loop {
        tauri::async_runtime::block_on(check(&app, false));
        std::thread::sleep(CHECK_EVERY);
    });
}

/// Look for a newer release. `manual` is true when the owner asked from the tray, so
/// "up to date" and errors are shown instead of only logged.
pub async fn check(app: &AppHandle, manual: bool) {
    let Ok(updater) = app.updater() else {
        return;
    };
    match updater.check().await {
        Ok(Some(update)) => {
            let version = update.version.clone();
            set_menu(app, &format!("Install update {version}"), true);
            if let Some(pending) = app.try_state::<Pending>() {
                *pending.update.lock().expect("update lock") = Some(update);
                let mut announced = pending.announced.lock().expect("update lock");
                if manual || announced.as_deref() != Some(version.as_str()) {
                    notify(
                        app,
                        &format!("NEXUS {version} is ready"),
                        "Choose Install update in the NEXUS tray menu when it suits you.",
                    );
                    *announced = Some(version);
                }
            }
        }
        Ok(None) => {
            set_menu(app, CHECK_LABEL, true);
            if manual {
                let current = app.package_info().version.to_string();
                notify(
                    app,
                    "NEXUS is up to date",
                    &format!("You have version {current}."),
                );
            }
        }
        Err(err) => {
            eprintln!("update check failed: {err}");
            set_menu(app, CHECK_LABEL, true);
            if manual {
                notify(app, "Couldn't check for updates", &err.to_string());
            }
        }
    }
}

/// The tray item: install the update that was found, or check if none was.
pub async fn on_menu(app: &AppHandle) {
    let pending = app
        .try_state::<Pending>()
        .and_then(|p| p.update.lock().expect("update lock").take());
    let Some(update) = pending else {
        set_menu(app, "Checking for updates…", false);
        check(app, true).await;
        return;
    };
    let version = update.version.clone();
    set_menu(app, &format!("Installing {version}…"), false);
    // The installer replaces the app's files, so the agent we started must stop first.
    crate::stop_agent(app);
    match update.download_and_install(|_, _| {}, || {}).await {
        Ok(()) => app.restart(),
        Err(err) => {
            eprintln!("update failed: {err}");
            notify(
                app,
                "The update didn't install",
                &format!("{err}. NEXUS will offer it again."),
            );
            if let Some(p) = app.try_state::<Pending>() {
                *p.update.lock().expect("update lock") = Some(update);
            }
            set_menu(app, &format!("Install update {version}"), true);
        }
    }
}
