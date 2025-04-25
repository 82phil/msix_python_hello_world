# https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-manual-conversion
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

parser = ArgumentParser()

parser.add_argument(
    "destination_dir",
    help="The desired directory where the AppxManifest and AppInstaller files will be placed.",
    default="."
)

parser.add_argument(
    "--app-version",
    help="The version of the application to be packaged.",
    required=True)

parser.add_argument(
    "--manifest",
    help="Manifest JSON file to build the AppxManifest and AppInstaller from.",
    metavar="FILE",
    required=True)

parser.add_argument(
    "--logo-dir",
    help="Directory containing the logos to be used in the MSIX package.",
    required=True)

parser.add_argument(
    "--cert-subject",
    dest="cert_subject",
    help="Provide the Code Signing Certificate Subject, otherwise the script will search for one.")

parser.add_argument(
    "--cert-path",
    dest="cert_path",
    help="Provide the Code Signing Certificate Subject, otherwise the script will search for one.")

parser.add_argument(
    "--no-manifest",
    dest="no_manifest",
    action="store_true",
    help="Do not generate an AppxManifest XML file.")

parser.add_argument(
    "--gen-installer",
    dest="gen_installer",
    action="store_true",
    help="Generate an AppInstaller XML file.")

parsed_args = parser.parse_args()

manifest = json.load(open(parsed_args.manifest, "r"))

print("Generating MSIX files...")


def get_cert_subject():
    """ Search for a code signing cert to use if not provided in the args. """

    if hasattr(parsed_args, "cert_subject") and parsed_args.cert_subject:
        return parsed_args.cert_subject

    cert_path = r"Cert:\LocalMachine\*"
    if hasattr(parsed_args, "cert_path") and parsed_args.cert_path:
        cert_path = parsed_args.cert_path

    # Find a valid code signing certificate that is not expired.
    # Note: Pulling the cert with the latest expiration date to ensure that the latest certs installed
    # will continue to work, better to find out early instead of when the earlier cert expires.
    # https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/get-childitem?view=powershell-7.3#example-7-get-all-certificates-with-code-signing-authority
    cert_code = rf""" \
        $certs = (Get-ChildItem -Path {cert_path} -Recurse -CodeSigningCert)
        $filter_valid_certs = $certs | Where-Object {{ $_.NotBefore -lt (Get-Date) -and $_.NotAfter -gt (Get-Date) }}
        $cert = ($filter_valid_certs | sort NotAfter)[-1]
        $cert.FriendlyName
        $cert.Thumbprint
        $cert.Subject
    """

    # Change line endings to semicolons, formatting the code to a PowerShell one-liner command.
    pwsh_cmd = ";".join(map(lambda x: x.strip(), cert_code.splitlines()))

    cert = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-NoLogo",
            "-Command",
            pwsh_cmd
        ],
        capture_output=True,
        check=True
    )
    pwsh_cert_output = cert.stdout.decode("utf-8").splitlines()
    assert len(pwsh_cert_output) == 3, f"Unexpected output from Powershell: {pwsh_cert_output}"
    cert_name, cert_thumbprint, cert_subject = pwsh_cert_output
    print(f"Using Code Signing Certificate:\n '{cert_name}': {cert_thumbprint}\n")
    return cert_subject


@dataclass
class AppLogo:
    logo_sq_44x44: str
    logo_sq_150x150: str
    bg_color: str


@dataclass
class CodeSigningCert:
    publisher: str


@dataclass
class MsixApplication:
    name: str
    displayed_name: str
    description: str
    version: str
    cert: CodeSigningCert
    arch: str
    logo: AppLogo
    entrypoint: str
    displayed_publisher: str
    min_windows_version: str
    max_windows_version_tested: str


@dataclass
class MsixInstaller:
    version: str
    installer_uri: str
    appx_uri: str
    hours_between_update_checks: int
    show_prompt: bool
    update_blocks_activation: bool
    automatic_background_task: bool
    force_update_from_any_version: bool


def setup_app_logos(logo_dir: Path, **kwargs):
    """ Copy the logo files to the MSIX package directory. """

    pkg_logos_dir = Path(parsed_args.destination_dir) / "msix_assets"
    pkg_logos_dir.mkdir(exist_ok=True)

    assert logo_dir.exists() and logo_dir.is_dir(), f"Logo directory not found: {logo_dir}"

    logo_sq_44x44 = logo_dir / "logo_44x44.png"
    logo_sq_150x150 = logo_dir / "logo_150x150.png"

    def check_and_copy_logo(logo_path: Path):
        assert logo_path.exists(), f"Expected Logo file not found: {logo_path}"
        # copy the file to the destination directory
        shutil.copy(logo_path, pkg_logos_dir)
        return str(Path("msix_assets") / logo_path.name)

    return AppLogo(
        logo_sq_44x44=check_and_copy_logo(logo_sq_44x44),
        logo_sq_150x150=check_and_copy_logo(logo_sq_150x150),
        **kwargs
    )


def gen_appx_manifest(app_spec: MsixApplication):
    # https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-manual-conversion
    package = ET.Element("Package")
    package.set("xmlns", "http://schemas.microsoft.com/appx/manifest/foundation/windows10")
    package.set("xmlns:uap", "http://schemas.microsoft.com/appx/manifest/uap/windows10")
    package.set("xmlns:uap10", "http://schemas.microsoft.com/appx/manifest/uap/windows10/10")
    package.set("xmlns:uap13", "http://schemas.microsoft.com/appx/manifest/uap/windows10/13")
    package.set(
        "xmlns:rescap",
        "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities")
    package.set("IgnorableNamespaces", "uap13")

    # These provide the identity and are the source of the Package Full Name (PFuN) of the application.
    # https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/package-identity-overview
    identity = ET.SubElement(package, "Identity")
    identity.set("Name", app_spec.name)
    identity.set("Version", app_spec.version)
    # !!! The publisher field must match the signing certificate subject exactly, including quotes!
    identity.set("Publisher", app_spec.cert.publisher)
    identity.set("ProcessorArchitecture", app_spec.arch)

    properties = ET.SubElement(package, "Properties")

    # These are presented to the user by the MSIX installer.
    ET.SubElement(properties, "DisplayName").text = app_spec.displayed_name
    ET.SubElement(properties, "PublisherDisplayName").text = app_spec.displayed_publisher
    ET.SubElement(properties, "Description").text = app_spec.description
    ET.SubElement(properties, "Logo").text = app_spec.logo.logo_sq_150x150

    resources = ET.SubElement(package, "Resources")
    ET.SubElement(resources, "Resource").set("Language", "en-us")

    dependencies = ET.SubElement(package, "Dependencies")
    target_fam = ET.SubElement(dependencies, "TargetDeviceFamily")
    target_fam.set("Name", "Windows.Desktop")
    # https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/app-package-requirements?pivots=store-installer-msix#supported-versions
    target_fam.set("MinVersion", app_spec.min_windows_version)
    target_fam.set("MaxVersionTested", app_spec.max_windows_version_tested)

    capabilities = ET.SubElement(package, "Capabilities")
    ET.SubElement(capabilities, "rescap:Capability").set("Name", "runFullTrust")

    applications = ET.SubElement(package, "Applications")
    application = ET.SubElement(applications, "Application")
    # Splitting the Package ID and taking the last part, note that this id, known as the package-relative
    # app ID (PRAID) only needs to be unique within this package.
    # https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/element-application
    application.set("Id", app_spec.name.split(".")[-1])
    application.set("Executable", app_spec.entrypoint)
    application.set("uap10:RuntimeBehavior", "packagedClassicApp")
    # TODO: Will need to test if Python bundled apps could be run using 'appContainer'
    # so the app could optionally not require full trust.
    # https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/element-application
    application.set("uap10:TrustLevel", "mediumIL")

    # These are used by Windows in areas like the taskbar, start menu, start tiles, etc.
    # https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/appxmanifestschema/element-visualelements
    visual_elements = ET.SubElement(application, "uap:VisualElements")
    visual_elements.set("DisplayName", app_spec.displayed_name)
    visual_elements.set("Description", app_spec.description)
    visual_elements.set("Square150x150Logo", app_spec.logo.logo_sq_150x150)
    visual_elements.set("Square44x44Logo", app_spec.logo.logo_sq_44x44)
    visual_elements.set("BackgroundColor", app_spec.logo.bg_color)

    return package


def gen_appx_installer(app_spec: MsixApplication, installer_spec: MsixInstaller):
    # https://learn.microsoft.com/en-us/uwp/schemas/appinstallerschema/schema-root
    app_installer = ET.Element("AppInstaller")
    app_installer.set("xmlns", "http://schemas.microsoft.com/appx/appinstaller/2018")
    app_installer.set("Version", installer_spec.version)
    app_installer.set("Uri", installer_spec.installer_uri)

    main_pkg = ET.SubElement(app_installer, "MainPackage")
    main_pkg.set("Name", app_spec.name)
    main_pkg.set("Publisher", app_spec.cert.publisher)
    main_pkg.set("Version", parsed_args.app_version)
    main_pkg.set("Uri", installer_spec.appx_uri)
    main_pkg.set("ProcessorArchitecture", app_spec.arch)

    update_settings = ET.SubElement(app_installer, "UpdateSettings")
    on_launch = ET.SubElement(update_settings, "OnLaunch")
    on_launch.set("HoursBetweenUpdateChecks", str(installer_spec.hours_between_update_checks))
    on_launch.set("ShowPrompt", str(installer_spec.show_prompt).lower())
    on_launch.set("UpdateBlocksActivation", str(installer_spec.update_blocks_activation).lower())

    if installer_spec.automatic_background_task:
        ET.SubElement(update_settings, "AutomaticBackgroundTask")

    if installer_spec.force_update_from_any_version:
        ET.SubElement(update_settings, "ForceUpdateFromAnyVersion").text = "true"

    return app_installer


appx_manifest = manifest["AppManifest"]
installer_manifest = manifest["AppInstaller"]

app = MsixApplication(
    name=appx_manifest["Identity"]["Name"],
    arch=appx_manifest["Identity"]["Arch"],
    version=parsed_args.app_version,
    displayed_name=appx_manifest["Properties"]["DisplayName"],
    description=appx_manifest["Properties"]["Description"],
    displayed_publisher=appx_manifest["Properties"]["PublisherDisplayName"],
    entrypoint=appx_manifest["Application"]["EntryPoint"],
    cert=CodeSigningCert(publisher=get_cert_subject()),
    logo=setup_app_logos(
        logo_dir=Path(parsed_args.logo_dir),
        bg_color=appx_manifest["VisualElements"]["BackgroundColor"]),
    min_windows_version=appx_manifest["Dependencies"]["MinVersion"],
    max_windows_version_tested=appx_manifest["Dependencies"]["MaxVersionTested"]
)


installer = MsixInstaller(
    version=installer_manifest["Version"],
    installer_uri=installer_manifest["Uri"],
    appx_uri=installer_manifest["MainPackage"]["Uri"],
    hours_between_update_checks=installer_manifest["UpdateSettings"]["OnLaunch"]["HoursBetweenUpdateChecks"],
    show_prompt=installer_manifest["UpdateSettings"]["OnLaunch"]["ShowPrompt"],
    update_blocks_activation=installer_manifest["UpdateSettings"]["OnLaunch"]["UpdateBlocksActivation"],
    automatic_background_task=installer_manifest["UpdateSettings"]["AutomaticBackgroundTask"],
    force_update_from_any_version=installer_manifest["UpdateSettings"]["ForceUpdateFromAnyVersion"]
)

dest_dir = Path(parsed_args.destination_dir)
assert dest_dir.exists() and dest_dir.is_dir(), f"Destination directory {dest_dir} does not exist"

if not parsed_args.no_manifest:

    tree = ET.ElementTree(gen_appx_manifest(app))
    ET.indent(tree)
    tree.write(dest_dir / "AppxManifest.xml", encoding="utf-8", xml_declaration=True)
    print("Generated AppxManifest")


if parsed_args.gen_installer:

    tree = ET.ElementTree(gen_appx_installer(app, installer))
    ET.indent(tree)
    app_installer_path = dest_dir / PurePosixPath(urlparse(installer.installer_uri).path).name
    app_installer_path.unlink(missing_ok=True)
    tree.write(app_installer_path, encoding="utf-8", xml_declaration=True)

    # Padding AppInstaller to work around bug in the Delivery Optimization service
    # where the service only downloads the exact bytes from the last time the file was downloaded
    # which can cause the XML to be truncated and the installer to fail.
    # https://github.com/microsoftdocs/msix-docs/issues/188#issuecomment-947934682
    # Also noted to be fixed with Win 10 19045.3030
    # https://blogs.windows.com/windows-insider/2023/05/11/releasing-windows-10-build-19045-3030-to-release-preview-channel/

    with open(app_installer_path, "ba") as f:
        # Get the current size of the file
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        file_pad_limit = 4096
        # 4k is an arbitrary limit, hopefully an order of magnitude larger
        # than the change in file size but if could be increased if needed, just
        # note that the Delivery Optimization service will need to be restarted
        # so it fully downloads the new file limit size.
        assert file_size < file_pad_limit, (
            f"AppInstaller file size is larger than the {file_pad_limit}B limit")
        # Pad the file to the limit
        f.write(b"\n" + b" " * ((file_pad_limit - 1) - file_size))
    print("Generated AppInstaller")

print("Completed Successfully!\n")
