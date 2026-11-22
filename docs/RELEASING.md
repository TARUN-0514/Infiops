# Releasing the Windows app

Installed copies of the Windows app check GitHub releases for updates. They only install
an update that is signed with your private key and names the version it was signed for.

## One-time setup

1. Make a signing key on your PC. Choose a password when it asks:
   ```powershell
   cd apps\desktop
   npx @tauri-apps/cli@2.12.6 signer generate -w $HOME\.tauri\nexus.key
   ```
2. In GitHub, open the repository's Settings › Secrets and variables › Actions.
   - **Secrets:** add `TAURI_SIGNING_PRIVATE_KEY`, with the contents of
     `nexus.key`. Add `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`, with the password you chose.
   - **Variables:** add `NEXUS_UPDATER_PUBKEY`, with the contents of `nexus.key.pub`.
3. Keep `nexus.key` and its password in your password manager too.
   - If you lose the key, installed apps can't update. You would have to install the next
     version by hand.
   - If the key leaks, make a new one, update the secret and variable, and reinstall the
     app by hand.

## Each release

1. Set the version and push a tag:
   ```bash
   scripts/bump-desktop-version.sh 0.2.0
   git commit -am "Windows app 0.2.0"
   git tag desktop-v0.2.0
   git push origin main desktop-v0.2.0
   ```
2. The **Desktop release** workflow then builds and signs the installer, and creates a
   **draft** release with three files:
   - `NEXUS_0.2.0_x64-setup.exe`
   - its `.sig` signature
   - `latest.json`
3. Install the draft's installer on your PC and check it works.
4. Press **Publish**. Within six hours, installed apps show "NEXUS 0.2.0 is ready", and
   install it when you choose **Install update** in the tray.

A build made on your own PC with `pnpm build` has no update key. That copy never checks
for updates, which is fine for trying changes.
