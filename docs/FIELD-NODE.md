# The field node: installing it and looking after it

StratiGraph Server · for whoever prepares the node that goes to the excavation
and looks after it during the campaign. No programming is needed; you will type
a handful of commands in a terminal, and each one is written here exactly as it
is typed.

## What a field node is

A **field node** is StratiGraph Server running on a laptop or a small computer
that travels with the team. It is the same server as the institutional node:
same rooms, same em.json, same roles. What changes is the situation: on the
excavation there is often no internet, so people sign in with a **field
password** that the node gives them, and the team arrives from the institutional
node in a **signed package** prepared before leaving.

Three kinds of node exist, and each node declares which one it is
(`EM_NODE_KIND`):

| Kind | What it is |
|----|----|
| `institutional` | The node of an institution, reachable on the internet under a public name. People sign in with ORCID. It prepares the packages for the field and receives them back. Installed by the institution's IT with the deployment playbook. |
| `field` | This page. A laptop or a box on the excavation, often offline. |
| `personal` | One person's computer; the files stay in their folders. Nothing to manage. |

The node holds you to the safe defaults of its kind and tells you, in the
console's *Node health* panel, what is still missing.

```{note}
Four commands install a field node: one downloads and installs, one sets it up
with your ORCID, one starts it the first time, one makes the computer trust
it. After that the node switches itself on with the computer.
```

## What you need

**The node computer**, one of:

- a **Raspberry Pi 5 with 8 GB** of memory, its official 27 W power supply, and
  an SSD (NVMe or USB) rather than the memory card for the data. Add the **RTC
  battery** (the small official battery that plugs into the board, a few euros):
  it keeps the clock running while the Pi is off, and the node needs the right
  time — see *The clock* below;
- or a Mac or a Linux laptop with at least 8 GB of memory and 100 GB of free
  disk.

**A network on the site**: a small travel router (access point). The node is
connected to it **by cable**; phones and tablets join its Wi-Fi. The router does
not need the internet. In its settings, once, at base:

- leave DHCP on (it gives addresses to the devices);
- switch off *client isolation* (sometimes called *AP isolation*): with it on,
  the phones cannot see the node;
- give the node a **fixed address** (DHCP reservation) and, if the router offers
  it, a local name equal to the node's name (`fcn.local`, say) — it helps phones
  that do not resolve `.local` names by themselves.

The node needs no Wi-Fi password: it is on the cable. The Wi-Fi password is the
router's, and the team receives it like any Wi-Fi password.

**At base, once**: an internet connection, your ORCID iD, and a contact at the
institutional node, the person who looks after it.

## Part 1 · Installing, at base

The whole installation is four commands, typed in a terminal on the node
computer (on a Pi without a screen: from another computer, `ssh` to it).

### Step 1 · Download and install

On a **Mac**, install Homebrew first (<https://brew.sh>). On a **Raspberry Pi**
or another Debian/Ubuntu Linux nothing is needed beforehand. Then:

```bash
curl -fsSL https://raw.githubusercontent.com/StratiGraph-ECCCH/stratigraph-server/main/dev-stack/fcn-get.sh | bash
```

It downloads the server into `~/stratigraph`, installs what the computer lacks
(Docker and the rest; it asks for your computer password once), downloads the
companion programs, and checks everything. It says, in plain words, anything it
could not do.

Running the same command again later, at base, **updates** the node.

Every command from here on is typed in the `dev-stack` folder:

```bash
cd ~/stratigraph/stratigraph-server/dev-stack
```

### Step 2 · Register the node with ORCID

The node must sign you in with ORCID once, at base, before it can give anybody a
field password: a node attests only the identities ORCID verified.

Sign in at <https://orcid.org>, open *Developer tools*, and register a public
API client with this redirect URI, where `NAME` is the node's network name — the
computer's name followed by `.local` (`fcn.local` for a Pi called `fcn`):

    https://NAME:8443/auth/realms/em-dev/broker/orcid/endpoint

Keep the *client ID* and the *client secret* at hand for the next step.

### Step 3 · Set the node up, once

```bash
./fcn-field-setup.sh
```

It asks, one at a time: your ORCID iD, your name, a name for the node that the
other nodes will read (`scavo-2027`), its network name (it proposes the
computer's), the ORCID client ID and secret (the secret does not show while you
type), and whether the node must **switch itself on** every time the computer is
switched on — answer yes.

Then it:

- generates the node's **own secrets**, long and random, and never prints them;
- declares the node a **field node**, with fictitious test people switched off;
- makes **you** its manager, by your ORCID iD;
- prepares the sign-in service **without demonstration accounts**.

Everything is written in `.env.dev`, readable only by you. Keep a copy of it in
a safe place (an encrypted USB stick, your institution's password manager):
without it the node cannot be rebuilt. Running the command again asks only what
is still missing — the ORCID client, for instance, if you skipped it.

### Step 4 · Start it, the first time

```bash
./fcn-up.sh
```

The first start downloads the programs ready-made (the images published on GHCR,
for Intel and ARM alike — see *[From the code, or from the published
images](../../stratigraph-server/docs/DEPLOYMENT.md#from-the-code-or-from-the-published-images)*
in the server's manual): nothing is built on the node, and only `stratigraph-server` is cloned
on it. It needs the internet this once — `./fcn-install.sh` has usually
downloaded them already. From then on the node starts by itself at every
power-on, in a few minutes, with or without a network.

Then make this computer trust the node's certificate (it asks for your computer
password):

```bash
./fcn-trust-ca.sh
```

and open <https://NAME:8443/em/rooms/> — the node's front door — in the browser.

### Step 5 · Become the node's manager

1.  Open the console, <https://NAME:8443/em/admin/> , and choose *Sign in with
    ORCID*. ORCID links your account the first time, and you enter as
    **super-administrator**.

2.  Give yourself the **field password** you will use on the excavation, where
    ORCID cannot be reached:

    ```bash
    ./offline-password.sh 0000-0000-0000-0000
    ```

    (your iD). It asks for the password twice and shows nothing on screen. At
    your first field sign-in the node asks you to choose your own.

3.  In *Node health*, the card *What kind of node* says **field node** and lists
    what is still missing. At this point it normally says that the node trusts
    no node yet: that is the next step.

### Step 6 · Exchange keys with the institutional node

The two nodes must trust each other once, so that the team's package can be
accepted. It is done by the two managers, on the phone or face to face.

1.  In the console, *Transfers*: the section *This node* shows the node's public
    key and its **fingerprint**. *Copy the key* and send it to the institutional
    node's manager by mail.
2.  The institutional manager does the same and sends you their key.
3.  In *Trusted nodes*, write the institutional node's name exactly as it
    declares itself, paste its key, *Add*.
4.  Read the two fingerprints aloud to each other. If they match, the trust is
    set. If they do not, remove the entry and start again: somebody pasted the
    wrong key.

### Step 7 · Bring the team in

1.  On the **institutional** node, its manager opens *Transfers → Prepare a
    package*, ticks the rooms that go to the field (and adds any other ORCID
    iD), and makes the package: a `.json` file, signed by that node. It travels
    by mail or USB stick.
2.  On the **field** node, *Transfers → Receive a package*, choose the file. The
    console shows who is in it, whether the signature is good and comes from a
    trusted node, and the profiles proposed. Untick anybody who is not coming;
    tick the profiles you accept; *Bring in*.
3.  In *People*, give each person their **field password**. It is temporary: the
    person chooses their own at the first sign-in.

Passwords never travel in a package: every person receives one from the node
they are working on.

### Step 8 · Prepare the phones and tablets

The camera, the microphone and the GPS work in the browser only on a connection
the device trusts. Every phone and tablet that will record must trust the node's
certificate, **at base**:

1.  On the node: `./fcn-trust-ca.sh --export-only` writes `caddy-em-root.crt` in
    your home folder. Send it to the devices (mail, AirDrop, cable).
2.  **iPhone and iPad** — two steps, in two different places: open the file and
    install the profile (*Settings → General → VPN & Device Management*); then
    *Settings → General → About → Certificate Trust Settings* and turn on full
    trust for it.
3.  **Android** — *Settings → Security → Encryption & credentials → Install a
    certificate → CA certificate*, and choose the file. Menu names vary a little
    between makers.
4.  Join the node's network and open <https://NAME:8443/em/rooms/> : the page
    opens without warnings.

## Part 2 · On the excavation

### Each morning

1.  Switch on the router, then the node computer. The node starts by itself:
    after a few minutes it answers.
2.  Open <https://NAME:8443/em/rooms/> on one device to check that it does.
    Everything you left the evening before is there: studies, rooms, files, and
    the people with their field passwords.

If it does not answer after five minutes, the record of the last start is in
`dev-stack/fcn-boot.log`; `./fcn-up.sh --offline` starts it by hand.

### Each evening

Switch the computer off the normal way (on a Pi: `sudo poweroff`, or the button
on the Pi 5). The node stops with it, gently, and keeps every datum. Pulling the
plug of a running Pi is what to avoid: the last minutes of work can be lost.
Copy the node's data to an external disk if your institution's procedure asks
for it.

```{warning}
`./fcn-down.sh --wipe` **erases** the node's data: studies, rooms, files,
accounts and the certificate. It exists for tests. It is never used on a node
that holds a campaign.
```

### The clock

The node and the phones must agree on the time: the node's certificate and every
sign-in carry a date, and a phone refuses a certificate that, by its own clock,
has expired. With the internet a computer sets its clock by itself; on the
excavation it cannot. A Mac or a laptop keeps time while off. A Raspberry Pi
keeps it **only with the RTC battery**: without it, every morning the Pi starts
from the time it was switched off, many hours behind, and the phones refuse the
node. With the battery in place, nothing to do.

### When somebody forgets the password

Console → *People* → the person → *Field password*: type a new temporary
password twice and tell it to the person. They choose their own at the next
sign-in. The act is written in the node's log; the password never is.

### When somebody joins the team on site

Add them in *People* by their ORCID iD. Without a network the node cannot verify
the iD, so they cannot receive a field password yet. Two ways out: they work
with a colleague's device until the network comes back, or, when somebody can
reach the internet for a moment (a phone hotspot is enough), they sign in once
with ORCID on the node and then receive their field password. On the way back
they arrive at the institutional node marked *to verify*.

### What the node tells you

*Node health* is the first panel to open when something looks wrong: every
service with its state, and on top the card *What kind of node* with what is
missing for a field node. A service *not configured* is not a failure; one that
*did not answer* is.

## Part 3 · Coming back

1.  **The people.** On the field node, *Transfers → Prepare a package* with the
    campaign's rooms; on the institutional node, *Receive a package*. People
    added on site arrive *to verify*; profiles raised on site arrive as
    proposals.
2.  **The studies.** The automatic synchronisation of rooms between nodes is
    being built. Until it arrives, each room's em.json is taken from the room
    (*em.json* door on the work page) and brought into the corresponding room of
    the institutional node, together with its files, by the room's owner.
3.  Keep the field node's data on an external disk until the institutional node
    has everything.

## Checklist before leaving

- `fcn-field-setup.sh` run before the first start, with your ORCID iD and the
  ORCID client; automatic start on.
- Switch the node off and on once at base: it comes back by itself.
- On a Raspberry Pi, the RTC battery in place.
- The router: client isolation off, the node on the cable with a fixed address.
- *Node health*: the card says **field node** and lists nothing in red.
- The institutional node is in *Trusted nodes*, fingerprints compared.
- The team's package received; every person has a field password, yours too.
- Every phone and tablet trusts the certificate and opens the node without
  warnings.
- The rooms for the campaign exist, with their people and roles.
- A copy of `.env.dev` in a safe place: it holds the node's secrets.

## What to keep private

The mechanism on this page is public. Some things of a real node are not: the
contents of `.env.dev`, the node's private key (`node-key.pem`, in the node's
data), the packages of people (they are personal data), the node's address and
its list of trusted nodes. See *Handle with care* in
[People, profiles and roles](../../stratigraph-server/docs/ROLES-AND-USERS.md#people-between-nodes),
in the server's manual.
