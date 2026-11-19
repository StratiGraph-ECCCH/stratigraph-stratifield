# StratiField

StratiField is the field assistant of the StratiGraph ecosystem: it records
stratigraphic units, photographs and observations from a trench, by voice or by
hand, and writes them into a room of a node — signed with the ORCID of whoever
spoke. It keeps working when the node is out of reach, and it runs on the node
that travels with the team.

This manual has two parts, like the server's: one for whoever works with it on
the excavation, one for whoever builds it or installs it. **Both are being
written**, and this page says what is here and what is not yet.

## Working in the field

You prepare the node that goes to the excavation, look after it during the
campaign, and bring the work home. How a room looks from inside — signing in,
sharing, roles — is the same on a field node as on any other, and is told once,
in [Working in a room](../../stratigraph-server/docs/ROOM-GUIDE.md) in the
server's manual.

```{toctree}
:maxdepth: 2
:caption: Working in the field

FIELD-NODE
```

**Not written yet:** a day in the trench with StratiField on the phone — opening
a room from its QR code, recording a unit by voice, attaching photographs, what
it says when it does not understand and what it does when the network goes.

## Building and running StratiField

You change StratiField's code, add a tool to it, or install it on a node.

**Not written yet, as pages.** What exists today is in the repository's
[README](../README.md), and it is where to read it until it moves here:

- [the tool contract](../README.md#the-centre-of-gravity-the-tool-contract),
  the shape that lets a partner add a capability with a descriptor and an
  adapter, and [the five MVP tools](../README.md#the-five-mvp-tools);
- [where a write lands](../README.md#where-a-write-lands) in the room's graph;
- [running it](../README.md#running-it) and its
  [configuration](../README.md#configuration);
- [hearing](../README.md#hearing-three-roads-and-the-node-says-which) and
  [interpreting](../README.md#interpreting-the-rules-first-a-model-second): the
  speech engine on the node, the rules before a model;
- [the image](../README.md#limmagine-e-il-passo-che-nessun-workflow-può-fare)
  and the step no workflow can do.

How a node is switched on — StratiField is one of its services — is
[Running a node](../../stratigraph-server/docs/DEPLOYMENT.md) in the server's
manual.
