I have a cad viewer that supports 2D drawing in these formats DWG, DXF, DWF, DGN
Got it. You have a CAD viewer for 2D drawings that supports:

DWG — common AutoCAD drawing format
DXF — Drawing Exchange Format, widely used for exchanging CAD data
DWF — Design Web Format, often used for publishing/reviewing drawings
DGN — MicroStation's drawing format
So your product can essentially upload/open and display 2D engineering or architectural drawings from multiple CAD ecosystems.

If you're describing this as a product capability, you could say:

The CAD Viewer supports viewing 2D drawings in DWG, DXF, DWF, and DGN formats, enabling users to access and review CAD files from multiple industry-standard sources.

If you tell me what you're trying to build or figure out with the viewer, I can help—for example: supported workflows, user stories, technical architecture, APIs, Elasticsearch/search integration, or product requirements.

I want to move towards displaying 3D cad drawings that are made from revit, in rvt format or IFC. my current doesn’t have the functionality to do so
Yes — this is a significant but very logical evolution of your product.

Your current viewer is essentially:

CAD files
DWG / DXF / DWF / DGN
        ↓
2D Viewer
        ↓
Display geometry
What you're moving toward is closer to:

BIM / 3D CAD files
RVT / IFC
        ↓
3D Model Processing / Translation
        ↓
Web-optimized 3D model
        ↓
3D Viewer
        ↓
Orbit / Zoom / Pan / Sections / Object selection
The important distinction: RVT vs IFC
RVT
RVT is the native Autodesk Revit project format.

It contains much more than just 3D geometry. A Revit model can contain:

Walls
Floors
Doors
Windows
Pipes
Electrical systems
Families
Materials
Parameters and metadata
Relationships between objects
Levels and phases
The challenge is that RVT is a proprietary format, so supporting it directly usually requires using technology that can read/translate Revit data.

IFC
IFC (Industry Foundation Classes) is a BIM interoperability format.

For your product, it may be a much easier format to start with because it was specifically designed to exchange building models between different BIM systems.

For example:

Revit
  ↓ Export
 IFC
  ↓
Your platform
  ↓
3D Viewer
That could be your first path to 3D support.

What "supporting 3D" actually means
You shouldn't think of this as simply adding:

"RVT and IFC" to the list of supported file extensions.

Your current system probably does something conceptually like:

Upload DWG
    ↓
CAD parsing/rendering engine
    ↓
2D geometry
    ↓
Browser viewer
For 3D BIM, you need several new capabilities.

1. File ingestion
The user uploads:

building.rvt
or:

building.ifc
Your system needs to identify the file type and send it through the appropriate processing pipeline.

2. Model translation
This is potentially the biggest architectural change.

You may need something like:

RVT ──────┐
          │
IFC ──────┼──→ Model Processing Service
          │
Other BIM ┘
                ↓
        Web-optimized 3D format
                ↓
             Viewer
You generally don't want the browser to receive and directly render a huge raw RVT file.

Instead, the backend/process service translates it into data optimized for streaming and rendering in a web viewer.

3. The actual 3D viewer
Your viewer now needs capabilities such as:

Rotate/orbit around the building
Zoom
Pan
Perspective/orthographic views
Object selection
Hide/isolate elements
Transparency
Section boxes / clipping planes
Floor/level navigation
Possibly measurements
Model tree/navigation
For example:

                    Building Model
                         │
              ┌──────────┴──────────┐
              │                     │
          Geometry               Metadata
              │                     │
          3D Renderer          Object Properties
              │                     │
              └──────────┬──────────┘
                         ↓
                    Web Viewer
A user could click a wall and see:

Element: Wall
Level: Floor 3
Material: Concrete
Height: 3.2m
Fire Rating: 2 hours
That's one of the major advantages of BIM compared with simply displaying a 3D mesh.

I would think about this as a product roadmap
Given that you already have a working 2D CAD viewer, I would not start with "support every feature of Revit."

I'd break it down.

Phase 1 — Display IFC
Goal:

A user can upload an IFC file and view the 3D model in the browser.

MVP features:

Upload IFC
Process model
Display 3D geometry
Orbit
Zoom
Pan
Basic model loading/progress state
IFC Upload
    ↓
Processing
    ↓
3D Model
    ↓
Browser
This proves the core technical capability.

Phase 2 — BIM navigation
Then add:

Select an object
Highlight an object
View metadata
Hide/show categories
Isolate objects
Model tree
Navigate between levels
Now the product becomes more than:

"I can see a 3D building."

It becomes:

"I can explore and inspect a BIM model."

Phase 3 — RVT support
Then you tackle:

RVT
 ↓
Translation / Conversion
 ↓
Your internal or web-optimized model representation
 ↓
Viewer
One possible product decision is whether you require:

RVT → IFC → Upload to your system
or whether users can simply upload:

RVT → Your system → Automatic processing → Viewer
The second is much better UX but significantly more technically complex.

The key question for your team
I think you should first determine what your current CAD viewer actually is architecturally.

Specifically:

Questions I'd ask your engineers
What rendering engine/library powers the current 2D viewer?
Does our existing viewer technology already have 3D capabilities?
Can it process IFC natively?
Can it process RVT directly, or would RVT require a conversion service?
Where does file processing happen today: browser, backend, or a separate service?
What is our current internal representation of a CAD drawing?
Could that architecture support 3D geometry and BIM metadata?
What are the expected model-size limitations?
Do we need server-side processing for large Revit models?
Would adding 3D mean extending the existing viewer or building a separate 3D/BIM pipeline?
From a PM perspective, your first task isn't choosing the technology
Your first task is to turn:

"We want to support Revit files"

into a precise problem.

For example:

Users currently working with Revit-based building models cannot view and inspect their 3D designs in our platform. We want to enable users to upload and interact with BIM models, initially supporting IFC and eventually native RVT files.

Then define the MVP:

A user can open an IFC model, navigate the model in 3D, select building elements, and inspect their basic properties.

That is a much clearer starting point for engineering discussions than simply:

"Add RVT support."

The most important thing I would investigate next is your current viewer technology. If you tell me what CAD viewer/vendor/library your product currently uses and roughly how your architecture works, I can help you map out exactly what would need to change to move from your current 2D DWG/DXF/DWF/DGN support toward IFC → 3D → RVT support.

Are there any open source stuff like so
Yes. There are open-source projects you can build on, especially for IFC. RVT is harder because Revit's format is proprietary and open-source RVT support is still relatively experimental.

My strongest candidates for your use case
1. xeokit — probably the closest match
xeokit SDK on GitHub

This is an open-source SDK specifically for web-based BIM/3D model viewing.

It supports workflows around:

IFC / BIM models
Large 3D models
Object selection
Metadata
Model hierarchy
Hide/show
X-ray/transparency
Sectioning
2D and 3D modes
Multiple models
They also have a more complete ready-made viewer:

xeokit BIM Viewer on GitHub

Conceptually, you could have:

IFC
 ↓
Conversion / processing
 ↓
xeokit-compatible model
 ↓
Your web application
 ↓
3D BIM Viewer
This is particularly interesting because you already have a CAD viewer. You might integrate the 3D viewer as a new capability rather than build the entire rendering engine yourself. xeokit's BIM viewer supports IFC2x3 and IFC4 and includes features such as tree views, object highlighting, hiding, X-ray, and sectioning. 

Important: its AGPL-3.0 licensing may matter significantly if your company's product is closed-source/commercial. The project offers a separate commercial licensing path. 

2. xeokit-bim-viewer — if you want something closer to a complete product
Instead of starting with just an SDK, look at the actual open-source viewer:

xeokit-bim-viewer repository

It already has a lot of what you might put in your requirements:

┌─────────────────────────────────────┐
│ Toolbar                             │
├──────────────┬──────────────────────┤
│              │                      │
│ Model Tree   │                      │
│              │     3D MODEL         │
│ Floors       │                      │
│              │    🏢                │
│ Elements     │                      │
│              │                      │
├──────────────┴──────────────────────┤
│ Properties / Metadata               │
└─────────────────────────────────────┘
Features include 3D/2D viewing, tree views by structure/type/storey, BCF viewpoints, sectioning, and object interactions. 

As a PM, I would definitely use this as a benchmark, even if your engineers don't adopt its code directly.

What about RVT?
This is where it gets more complicated.

There are interesting open-source projects such as:

rvt-rs on GitHub

and:

Reviter on GitHub

These projects attempt to read and inspect native .rvt files and can render or extract some geometry. For example, rvt-rs describes itself as an open reader for RVT-family formats and includes an experimental browser viewer/export capabilities, while Reviter explicitly describes its native RVT geometry recovery as experimental and limited by version/model support. 

So I wouldn't currently recommend basing a production enterprise feature solely on an experimental open-source RVT parser without extensive testing against your customers' actual Revit files.

How I would approach this in your product
Option A — Start with IFC ⭐ My recommendation
Revit
  │
  │ Export IFC
  ▼
Your existing platform
  │
  ├── Store IFC
  │
  ├── Process / convert
  │
  ▼
Open-source 3D Viewer
  │
  ▼
User explores BIM model
You could use something like xeokit for the viewing layer.

This gets you to:

"Our platform supports viewing 3D BIM models."

without immediately needing to solve:

"How do we fully and reliably decode every version of Autodesk's proprietary RVT format?"

Option B — Support RVT through conversion
Later:

User uploads RVT
       ↓
RVT Conversion Service
       ↓
IFC / GLB / internal format
       ↓
3D Viewer
The user gets native RVT upload support, but internally your viewer doesn't necessarily need to understand RVT directly.

This distinction is important:

"Support RVT upload"
        ≠
"Browser directly renders RVT"
A mature architecture might look like:

              ┌── DWG ──→ 2D Pipeline ──┐
              ├── DXF ──→ 2D Pipeline ──┤
User Upload ──┤                         ├──→ Unified Viewer Platform
              ├── IFC ──→ 3D Pipeline ──┤
              └── RVT ──→ Convert ──────┘
                              ↓
                         3D Pipeline
My recommendation for your next investigation
I would ask your engineers:

Could we prototype IFC support using an existing open-source viewer such as xeokit, and what would be required to integrate it into our current viewer architecture?

Then investigate these four things:

Can we display an IFC model with the open-source technology?
How large are our customers' typical Revit/IFC models?
Can we preserve BIM metadata and element IDs after conversion?
What would it take to eventually add RVT upload?
If you want, I can next make you a proper comparison table of the main open-source options—for example xeokit vs web-ifc/That Open Engine vs Three.js-based approaches, including file support, architecture, performance, licensing, RVT support, and which one I'd recommend for your existing product.

Is there a way to transform 2D cad files like DWG / DXF into IFC
Yes, but there is an important catch:

You can transform a 2D DWG/DXF into an IFC file, but you usually cannot automatically turn it into a true 3D BIM model.

These are fundamentally different types of information.

Why?
Imagine your DWG contains this:

┌───────────────────┐
│                   │
│     ROOM          │
│                   │
├───────     ───────┤
│                   │
└───────────────────┘
A 2D DWG might only tell you:

Here are lines
These lines are on certain layers
Here is text saying "ROOM"
Here is a symbol that might represent a door
It doesn't necessarily tell you:

This is an IfcWall
Height = 3 meters
Material = concrete
This is an IfcDoor
This is an IfcSpace called Room
But IFC is designed to represent those semantic building objects and their relationships, not just geometry. 

So the conversion problem is really:
DWG / DXF
   ↓
Lines, arcs, blocks, layers, text
   ↓
??? ← interpretation is required
   ↓
Walls, doors, spaces, columns
   ↓
IFC
That ??? is the difficult part.

There are basically 3 levels of conversion
1. Geometry-only conversion — easiest
You could convert:

DWG / DXF
    ↓
Read geometry
    ↓
Create IFC entities containing that geometry
    ↓
output.ifc
But the resulting IFC might effectively say:

"Here is some geometry."

rather than:

"This is a wall, this is a door, and this room belongs to Floor 2."

This may still be useful if your goal is displaying the drawing in an IFC-capable ecosystem, but it doesn't magically create BIM intelligence.

2. Rule-based conversion — potentially very interesting for your product
Suppose your customers' DWG files follow conventions:

Layer: A-WALL
    ↓
Interpret as walls

Layer: A-DOOR
    ↓
Interpret as doors

Layer: A-COLUMN
    ↓
Interpret as columns
Then you could build a conversion pipeline:

DWG
 ↓
Extract entities + layers
 ↓
Apply mapping rules
 ↓
A-WALL   → IfcWall
A-DOOR   → IfcDoor
A-COLUMN → IfcColumn
 ↓
Generate IFC
For example:

Input DWG:

Layer A-WALL:
    ────────────────

Layer A-DOOR:
         ║

        ↓

Generated IFC:

IfcWall
    geometry: ...

IfcDoor
    geometry: ...
This is much more feasible than trying to blindly understand every arbitrary CAD drawing.

The quality would depend heavily on how consistently your users structure their CAD files.

3. AI/Computer Vision-assisted BIM reconstruction — hardest
Potentially:

DWG
 ↓
Geometry extraction
 ↓
AI / rules
 ↓
"These parallel lines look like a wall"
"This symbol looks like a door"
 ↓
Create BIM elements
 ↓
Infer heights / levels / relationships
 ↓
3D IFC
But now you're effectively trying to reconstruct a BIM model from a 2D drawing.

A 2D floor plan usually doesn't contain enough information to know, for example:

Wall height
Ceiling geometry
Floor thickness
Structural depth
Exact 3D position of elements
What exists above/below that floor
So some information must be inferred or supplied by the user.

Open-source starting points
IfcOpenShell is particularly relevant here. It's an open-source library that can create, read, edit, and write IFC files through C++ and Python APIs. 

However, one important clarification from my previous answer: IfcConvert itself is primarily for converting IFC outward into other formats; its documented workflow is not a general-purpose DWG/DXF → IFC converter. 

There is, however, an IfcOpenShell community example for a dxf2ifc.py script, which is a useful starting point for understanding a custom DXF → IFC pipeline. 

You could conceptually build this in Python:

DXF
 ↓
DXF parser
 ↓
Extract:
- lines
- polylines
- arcs
- blocks
- layers
- text
 ↓
Your interpretation logic
 ↓
IfcOpenShell
 ↓
IFC
For DWG, you might first normalize it to DXF using a tool such as ODA File Converter, which officially converts between DWG and DXF versions, then run your own DXF → IFC logic. 

For your specific product, I see a potentially interesting strategy
Since you already support viewing DWG and DXF, you could potentially reuse the information your current CAD processing pipeline already extracts:

              CURRENT PRODUCT

DWG/DXF ─────→ CAD Processing ─────→ 2D Viewer
                    │
                    │
                    ▼
              CAD entity data
              layers / geometry
                    │
                    ▼
              BIM interpretation
                    │
             ┌──────┴──────┐
             ▼             ▼
         Rules          AI later
             │             │
             └──────┬──────┘
                    ▼
              IFC Generator
                    ▼
               3D IFC Model
                    ▼
                3D Viewer
My recommendation
I wouldn't frame this initially as:

"Can we convert DWG to IFC?"

I would frame it as:

"Can we reconstruct a useful IFC/BIM representation from the structured information available in our existing 2D CAD files?"

That leads to much better questions for your engineers:

What information does our current DWG/DXF parser already extract?
Do we have access to layers and CAD entity types?
Can we identify blocks and their attributes?
Do our customers use consistent layer naming conventions?
Can we map specific layers/entities to IFC classes?
Do we have enough information to create 2.5D/3D geometry, or would users need to provide heights?
Could we create an IFC export/conversion service using IfcOpenShell?
The biggest product opportunity, in my opinion, is not a universal "DWG → IFC converter." It's a CAD-to-BIM conversion pipeline optimized for the types of drawings your users actually upload. If their drawings are standardized, this could be dramatically more achievable.

