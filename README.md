# 'Hello World' Python MSIX App Demo

A simple demonstration on how to take a Python App, build it into an executable,
and then package it using MSIX for distribution.

## Build the .exe

PyInstaller makes this part easy, just install the package and run make.

```powershell
PS> pip install -r requirements.txt
PS> .\make.bat
```

## Run the .exe

```powershell
PS> .\dist\demo\demo.exe
Hello World!
```

## Build the MSIX package

Read through the [Python Desktop App Distribution Using MSIX]() post to get all
the pre-requisites sorted out, then it is just a few commands to build and sign
the package.

```powershell
PS> python .\gen_msix_xml.py --app-version 1.0.0.0 --manifest .\manifest.json --logo-dir .\logos .\dist\demo\
PS> makeappx.exe pack /d .\dist\demo\ /p demo.msix
# Run the following as admin
PS> signtool sign /fd sha256 /v /sm /s TrustedPeople /a /t http://timestamp.digicert.com .\demo.msix
```

## Try it out

```powershell
PS> .\demo.msix
```

# Overview

The `gen_msix_xml.py` script handles generating the `AppxManifest.xml` required by
`makeappx` to build an MSIX package so you don't have to.

The following are required arguments:

<table>
  <tr>
    <td><span style="white-space: nowrap;"><code>--app-version</code></span></td>
    <td>
      Follows the format of <code>major.minor.patch.build</code><br />
      Build should be a monotonic number that, for instance, increments with
      each run of the continuous integration job that builds the MSIX package.
      The app version needs to change to indicate an update.
    </td>
  </tr>
  <tr>
    <td><span style="white-space: nowrap;"><code>--logo-dir</code></span></td>
    <td>
      Images used by Windows in areas like the taskbar, start menu, start tiles, etc.
    </td>
  </tr>
  <tr>
    <td><span style="white-space: nowrap;"><code>--manifest</code></span></td>
    <td>
      Path to the <code>.json</code> file that contains information necessary to
      build the <code>AppxManifest.xml</code> and <code>.AppInstaller</code>
      files and closely match the corresponding XML attributes. See
      <code>manifest.json</code> in the project for an example.
    </td>
  </tr>
</table>

In addition there are options to specify the appropriate signing cert to use and
generating the `.AppInstaller` manifest as well.

```powershell
python .\gen_msix_xml.py --help
usage: gen_msix_xml.py [-h] --app-version APP_VERSION --manifest FILE
                       --logo-dir LOGO_DIR [--cert-subject CERT_SUBJECT]
                       [--cert-path CERT_PATH] [--no-manifest]
                       [--gen-installer]
                       destination_dir

positional arguments:
  destination_dir       The desired directory where the AppxManifest and
                        AppInstaller files will be placed.

optional arguments:
  -h, --help            show this help message and exit
  --app-version APP_VERSION
                        The version of the application to be packaged.
  --manifest FILE       Manifest JSON file to build the AppxManifest and
                        AppInstaller from.
  --logo-dir LOGO_DIR   Directory containing the logos to be used in the MSIX
                        package.
  --cert-subject CERT_SUBJECT
                        Provide the Code Signing Certificate Subject,
                        otherwise the script will search for one.
  --cert-path CERT_PATH
                        Provide the Code Signing Certificate Subject,
                        otherwise the script will search for one.
  --no-manifest         Do not generate an AppxManifest XML file.
  --gen-installer       Generate an AppInstaller XML file.

```