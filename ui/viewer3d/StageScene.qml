import QtQuick
import QtQuick3D
import QtQuick3D.Helpers
import QtQuick.Controls

/* ═══════════════════════════════════════════════════════════════
   StageScene.qml — Viewer 3D per stage IPSC
   ═══════════════════════════════════════════════════════════════ */

Rectangle {
    id: root
    color: "#1e293b"

    /* ---- Proprietà ---- */
    property real floorWidth: stageWidth
    property real floorDepth: stageDepth
    property bool fpMode: false
    property real panSpeed: 6.0
    property real zoomSpeed: 2.0
    property real gravity: -9.8
    property real playerHeight: 1.7  // altezza occhi

    /* ---- Segnali ---- */
    signal requestFullscreen()

    /* ─────────────────────────────────────────────────
       FUNZIONI
       ───────────────────────────────────────────────── */
    function resetOrbitCamera() {
        orbitCamera.position = Qt.vector3d(floorWidth / 2, 12, floorDepth + 8);
        orbitCamera.eulerRotation = Qt.vector3d(-35, 0, 0);
        orbitOrigin.position = Qt.vector3d(floorWidth / 2, 0, floorDepth / 2);
    }

    function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

    /* ─────────────────────────────────────────────────
       COLLISION DETECTION (FP mode)
       ───────────────────────────────────────────────── */
    function checkCollision(x, z, radius) {
        var objects = stage3dModel.objects;
        var r = radius || 0.2;
        for (var i = 0; i < objects.length; i++) {
            var o = objects[i];
            if (!o.collidable) continue;
            // AABB approssimato
            var ox = o.x, oz = o.z;
            var ow = (o.sx || 1.0) / 2 + r;
            var oz_half = (o.sz || 0.1) / 2 + r;
            if (Math.abs(x - ox) < ow && Math.abs(z - oz) < oz_half) {
                return true;
            }
        }
        return false;
    }

    // Movimento con slide collisione
    function moveWithCollision(dx, dz) {
        var nx = fpCamera.position.x + dx;
        var nz = fpCamera.position.z + dz;

        // Boundary: non uscire dallo stage
        var margin = 0.3;
        nx = clamp(nx, margin, floorWidth - margin);
        nz = clamp(nz, margin, floorDepth - margin);

        // Test collisione X e Z separatamente per slide
        if (!checkCollision(nx, fpCamera.position.z)) {
            fpCamera.position.x = nx;
        }
        if (!checkCollision(fpCamera.position.x, nz)) {
            fpCamera.position.z = nz;
        }
    }

    /* ═══════════════════════════════════════════════════
       KEY INPUT (condiviso orbita/FP)
       ═══════════════════════════════════════════════════ */
    Item {
        id: keyInput
        focus: true
        anchors.fill: parent

        Component.onCompleted: forceActiveFocus()

        property bool moveForward: false
        property bool moveBack: false
        property bool moveLeft: false
        property bool moveRight: false
        property bool sprint: false
        property bool jump: false
        property real yaw: 0
        property real pitch: 0

        Keys.onPressed: (event) => {
            if (!root.fpMode) {
                switch(event.key) {
                    case Qt.Key_W:
                    case Qt.Key_Up:    moveForward = true; break;
                    case Qt.Key_S:
                    case Qt.Key_Down:  moveBack = true; break;
                    case Qt.Key_A:
                    case Qt.Key_Left:  moveLeft = true; break;
                    case Qt.Key_D:
                    case Qt.Key_Right: moveRight = true; break;
                    case Qt.Key_Q:
                    case Qt.Key_PageUp: {
                        var fwd = orbitOrigin.position.minus(orbitCamera.position).normalized();
                        orbitCamera.position = orbitCamera.position.plus(fwd.times(root.zoomSpeed));
                        break;
                    }
                    case Qt.Key_E:
                    case Qt.Key_PageDown: {
                        var bwd = orbitCamera.position.minus(orbitOrigin.position).normalized();
                        orbitCamera.position = orbitCamera.position.plus(bwd.times(root.zoomSpeed));
                        break;
                    }
                    case Qt.Key_Home:
                    case Qt.Key_R: resetOrbitCamera(); break;
                    case Qt.Key_F11: root.requestFullscreen(); break;
                }
            } else {
                switch(event.key) {
                    case Qt.Key_W: moveForward = true; break;
                    case Qt.Key_S: moveBack = true; break;
                    case Qt.Key_A: moveLeft = true; break;
                    case Qt.Key_D: moveRight = true; break;
                    case Qt.Key_Shift: sprint = true; break;
                    case Qt.Key_Space: jump = true; break;
                    case Qt.Key_F11: root.requestFullscreen(); break;
                }
            }
        }
        Keys.onReleased: (event) => {
            if (!root.fpMode) {
                switch(event.key) {
                    case Qt.Key_W:
                    case Qt.Key_Up:    moveForward = false; break;
                    case Qt.Key_S:
                    case Qt.Key_Down:  moveBack = false; break;
                    case Qt.Key_A:
                    case Qt.Key_Left:  moveLeft = false; break;
                    case Qt.Key_D:
                    case Qt.Key_Right: moveRight = false; break;
                }
            } else {
                switch(event.key) {
                    case Qt.Key_W: moveForward = false; break;
                    case Qt.Key_S: moveBack = false; break;
                    case Qt.Key_A: moveLeft = false; break;
                    case Qt.Key_D: moveRight = false; break;
                    case Qt.Key_Shift: sprint = false; break;
                    case Qt.Key_Space: jump = false; break;
                }
            }
        }

        // Timer movimento orbitale
        Timer {
            interval: 16
            running: !root.fpMode
            repeat: true
            onTriggered: {
                var speed = root.panSpeed * (interval / 1000);
                var ry = orbitCamera.eulerRotation.y * Math.PI / 180;
                var fx = -Math.sin(ry);
                var fz = -Math.cos(ry);
                var rx = -Math.sin(ry + Math.PI/2);
                var rz = -Math.cos(ry + Math.PI/2);

                var dx = 0, dz = 0;
                if (keyInput.moveForward) { dx += fx * speed; dz += fz * speed; }
                if (keyInput.moveBack)    { dx -= fx * speed; dz -= fz * speed; }
                if (keyInput.moveLeft)    { dx += rx * speed; dz += rz * speed; }
                if (keyInput.moveRight)   { dx -= rx * speed; dz -= rz * speed; }

                orbitOrigin.position.x += dx;
                orbitOrigin.position.z += dz;
            }
        }

        // Timer movimento FP con collisioni e head bobbing
        Timer {
            id: fpTimer
            interval: 16
            running: root.fpMode
            repeat: true

            property real bobPhase: 0
            property real bobY: 0
            property real bobRot: 0

            onTriggered: {
                var speed = 3.0 * (keyInput.sprint ? 2.0 : 1.0) * (interval / 1000);
                var ry = fpCamera.eulerRotation.y * Math.PI / 180;
                var fx = -Math.sin(ry);
                var fz = -Math.cos(ry);
                var rx = -Math.sin(ry + Math.PI/2);
                var rz = -Math.cos(ry + Math.PI/2);

                var isMoving = keyInput.moveForward || keyInput.moveBack
                               || keyInput.moveLeft || keyInput.moveRight;

                var dx = 0, dz = 0;
                if (keyInput.moveForward) { dx += fx * speed; dz += fz * speed; }
                if (keyInput.moveBack)    { dx -= fx * speed; dz -= fz * speed; }
                if (keyInput.moveLeft)    { dx += rx * speed; dz += rz * speed; }
                if (keyInput.moveRight)   { dx -= rx * speed; dz -= rz * speed; }

                // Applica movimento con collisioni
                root.moveWithCollision(dx, dz);

                // Head bobbing
                if (isMoving) {
                    var freq = keyInput.sprint ? 14.0 : 10.0;
                    bobPhase += (freq * interval / 1000) * Math.PI * 2;
                    bobY = Math.sin(bobPhase) * 0.025;
                    bobRot = Math.sin(bobPhase * 0.5) * 0.3;
                } else {
                    bobY *= 0.85;  // decadimento
                    bobRot *= 0.85;
                }

                fpCamera.position.y = root.playerHeight + bobY;
                fpCamera.eulerRotation.z = bobRot;
            }
        }
    }

    /* ═══════════════════════════════════════════════════
       VIEW 3D
       ═══════════════════════════════════════════════════ */
    View3D {
        id: view3d
        anchors.fill: parent
        camera: root.fpMode ? fpCamera : orbitCamera
        environment: SceneEnvironment {
            clearColor: "#1e293b"
            backgroundMode: SceneEnvironment.Color
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
            probeExposure: 1.0
        }

        Node {
            id: scene

            /* ─── LUCI ─── */
            DirectionalLight {
                id: sun
                color: "#fff8e7"
                ambientColor: "#3a4050"
                brightness: 1.4
                eulerRotation.x: -50
                eulerRotation.y: 35
                shadowFactor: 50
                shadowMapQuality: Light.ShadowMapQualityMedium
                castsShadow: true
            }

            // Luce di riempimento (controluce)
            DirectionalLight {
                color: "#8899bb"
                ambientColor: "#222233"
                brightness: 0.3
                eulerRotation.x: 30
                eulerRotation.y: -150
            }

            Node {
                id: orbitOrigin
                position: Qt.vector3d(floorWidth / 2, 0, floorDepth / 2)
            }

            PerspectiveCamera {
                id: orbitCamera
                position: Qt.vector3d(floorWidth / 2, 12, floorDepth + 8)
                eulerRotation.x: -35
                clipNear: 0.1
                clipFar: 1000
            }

            PerspectiveCamera {
                id: fpCamera
                position: Qt.vector3d(2, root.playerHeight, 2)
                eulerRotation: Qt.vector3d(0, 0, 0)
                clipNear: 0.1
                clipFar: 1000
            }

            /* ─── PAVIMENTO CON TEXTURE ─── */
            Model {
                source: "#Cube"
                position: Qt.vector3d(floorWidth / 2, -0.05, floorDepth / 2)
                scale: Qt.vector3d(floorWidth, 0.1, floorDepth)
                materials: [ PrincipledMaterial {
                    baseColorMap: Texture {
                        source: tex_floor_concrete
                        scaleU: floorWidth / 4
                        scaleV: floorDepth / 4
                        tilingModeHorizontal: Texture.Repeat
                        tilingModeVertical: Texture.Repeat
                    }
                    baseColor: "#ffffff"
                    roughness: 0.85
                    normalStrength: 0.5
                }]
            }

            /* ─── GRIGLIA PAVIMENTO ─── */
            Repeater3D {
                model: Math.floor(floorWidth) + 1
                Model {
                    source: "#Cube"
                    position: Qt.vector3d(index, 0.002, floorDepth / 2)
                    scale: Qt.vector3d(0.02, 0.02, floorDepth)
                    materials: [ PrincipledMaterial {
                        baseColor: "#475569"
                        roughness: 1.0
                        opacity: 0.6
                    }]
                }
            }
            Repeater3D {
                model: Math.floor(floorDepth) + 1
                Model {
                    source: "#Cube"
                    position: Qt.vector3d(floorWidth / 2, 0.002, index)
                    scale: Qt.vector3d(floorWidth, 0.02, 0.02)
                    materials: [ PrincipledMaterial {
                        baseColor: "#475569"
                        roughness: 1.0
                        opacity: 0.6
                    }]
                }
            }

            /* ─── PARAPALLE (BACKSTOP) ─── */
            Model {
                source: "#Cube"
                position: Qt.vector3d(floorWidth / 2, 2.5, floorDepth + 0.15)
                scale: Qt.vector3d(floorWidth + 2.0, 5.0, 0.3)
                materials: [ PrincipledMaterial {
                    baseColorMap: Texture {
                        source: tex_backstop_earth
                        scaleU: (floorWidth + 2) / 3
                        scaleV: 5 / 3
                        tilingModeHorizontal: Texture.Repeat
                        tilingModeVertical: Texture.Repeat
                    }
                    baseColor: "#5c3a1e"
                    roughness: 0.95
                }]
            }
            Model {
                source: "#Cube"
                position: Qt.vector3d(-0.15, 2.5, floorDepth / 2)
                scale: Qt.vector3d(0.3, 5.0, floorDepth)
                materials: [ PrincipledMaterial {
                    baseColorMap: Texture {
                        source: tex_backstop_earth
                        scaleU: 0.3
                        scaleV: floorDepth / 3
                        tilingModeHorizontal: Texture.Repeat
                        tilingModeVertical: Texture.Repeat
                    }
                    baseColor: "#5c3a1e"
                    roughness: 0.95
                }]
            }
            Model {
                source: "#Cube"
                position: Qt.vector3d(floorWidth + 0.15, 2.5, floorDepth / 2)
                scale: Qt.vector3d(0.3, 5.0, floorDepth)
                materials: [ PrincipledMaterial {
                    baseColorMap: Texture {
                        source: tex_backstop_earth
                        scaleU: 0.3
                        scaleV: floorDepth / 3
                        tilingModeHorizontal: Texture.Repeat
                        tilingModeVertical: Texture.Repeat
                    }
                    baseColor: "#5c3a1e"
                    roughness: 0.95
                }]
            }

            /* ─── ZONA PARTENZA ─── */
            Model {
                source: "#Rectangle"
                position: Qt.vector3d(floorWidth / 2, 0.005, 1.0)
                scale: Qt.vector3d(2.0, 1.0, 2.0)
                eulerRotation.x: -90
                materials: [ PrincipledMaterial {
                    baseColor: "#15803d"
                    roughness: 0.8
                    opacity: 0.5
                }]
            }

            /* ─── FRECCE DIREZIONALI ─── */
            Model {
                source: "#Cone"
                position: Qt.vector3d(floorWidth / 2, 0.6, -0.5)
                scale: Qt.vector3d(0.5, 0.8, 0.5)
                eulerRotation.x: 90
                materials: [ PrincipledMaterial {
                    baseColor: "#22c55e"
                    roughness: 0.5
                }]
            }
            Model {
                source: "#Cone"
                position: Qt.vector3d(floorWidth / 2, 0.6, floorDepth + 0.5)
                scale: Qt.vector3d(0.5, 0.8, 0.5)
                eulerRotation.x: -90
                materials: [ PrincipledMaterial {
                    baseColor: "#ef4444"
                    roughness: 0.5
                }]
            }

            /* =====================================================
               OGGETTI STAGE CON MATERIALI PBR
               ===================================================== */
            Repeater3D {
                id: stageObjects
                model: stage3dModel.objects

                delegate: Node {
                    id: objNode
                    position: Qt.vector3d(modelData.x, modelData.y, modelData.z)

                    required property var modelData

                    // Seleziona materiale in base a modelData.mat
                    readonly property var materialComponent: {
                        var matName = modelData.mat || "generic";
                        switch (matName) {
                            case "wall":
                                return Qt.createQmlObject(`
                                    import QtQuick3D;
                                    PrincipledMaterial {
                                        baseColorMap: Texture { source: tex_wall_drywall }
                                        baseColor: "#e2e8f0"
                                        roughness: 0.75
                                        metalness: 0.0
                                        normalStrength: 0.3
                                    }
                                `, objNode, "wallMat");
                            case "target":
                                return Qt.createQmlObject(`
                                    import QtQuick3D;
                                    PrincipledMaterial {
                                        baseColorMap: Texture { source: tex_target_ipsc }
                                        baseColor: "#ffffff"
                                        roughness: 0.65
                                        metalness: 0.0
                                    }
                                `, objNode, "targetMat");
                            case "steel":
                                return Qt.createQmlObject(`
                                    import QtQuick3D;
                                    PrincipledMaterial {
                                        baseColorMap: Texture { source: tex_steel_metal }
                                        baseColor: "#9ca3af"
                                        roughness: 0.3
                                        metalness: 0.85
                                    }
                                `, objNode, "steelMat");
                            case "noshoot":
                                return Qt.createQmlObject(`
                                    import QtQuick3D;
                                    PrincipledMaterial {
                                        baseColor: "#eab308"
                                        roughness: 0.7
                                        metalness: 0.0
                                    }
                                `, objNode, "noShootMat");
                            case "barrier":
                                return Qt.createQmlObject(`
                                    import QtQuick3D;
                                    PrincipledMaterial {
                                        baseColorMap: Texture { source: tex_wood_planks }
                                        baseColor: "#a16207"
                                        roughness: 0.8
                                        metalness: 0.0
                                        normalStrength: 0.4
                                    }
                                `, objNode, "barrierMat");
                            case "door":
                                return Qt.createQmlObject(`
                                    import QtQuick3D;
                                    PrincipledMaterial {
                                        baseColorMap: Texture { source: tex_wood_porte }
                                        baseColor: "#713f12"
                                        roughness: 0.7
                                        metalness: 0.0
                                    }
                                `, objNode, "doorMat");
                            case "hard_cover":
                                return Qt.createQmlObject(`
                                    import QtQuick3D;
                                    PrincipledMaterial {
                                        baseColorMap: Texture { source: tex_hard_cover }
                                        baseColor: "#1e293b"
                                        roughness: 0.5
                                        metalness: 0.6
                                        normalStrength: 0.5
                                    }
                                `, objNode, "hardCoverMat");
                            case "soft_cover":
                                return Qt.createQmlObject(`
                                    import QtQuick3D;
                                    PrincipledMaterial {
                                        baseColorMap: Texture { source: tex_soft_cover }
                                        baseColor: "#4a5d23"
                                        roughness: 0.9
                                        metalness: 0.0
                                    }
                                `, objNode, "softCoverMat");
                            case "fault":
                                return Qt.createQmlObject(`
                                    import QtQuick3D;
                                    PrincipledMaterial {
                                        baseColor: "#dc2626"
                                        roughness: 0.6
                                        metalness: 0.0
                                        opacity: 0.8
                                    }
                                `, objNode, "faultMat");
                            default:
                                return Qt.createQmlObject(`
                                    import QtQuick3D;
                                    PrincipledMaterial {
                                        baseColor: modelData.color || "#808080"
                                        roughness: 0.6
                                    }
                                `, objNode, "genericMat");
                        }
                    }

                    Model {
                        source: "#Cube"
                        scale: Qt.vector3d(modelData.sx, modelData.sy, modelData.sz)
                        eulerRotation.y: modelData.rotation || 0
                        materials: [ materialComponent ]

                        // ── Animazione Swinger ──
                        SequentialAnimation on eulerRotation.y {
                            running: modelData.mat === "target"
                                    && modelData.amplitude !== undefined
                            loops: Animation.Infinite
                            RotationAnimation {
                                from: (modelData.rotation || 0) - (modelData.amplitude || 45)
                                to: (modelData.rotation || 0) + (modelData.amplitude || 45)
                                duration: 2000 / (modelData.speed || 1.0)
                            }
                            RotationAnimation {
                                from: (modelData.rotation || 0) + (modelData.amplitude || 45)
                                to: (modelData.rotation || 0) - (modelData.amplitude || 45)
                                duration: 2000 / (modelData.speed || 1.0)
                            }
                        }

                        // ── Animazione Mover ──
                        SequentialAnimation on position {
                            running: modelData.mat === "target"
                                    && modelData.distance !== undefined
                            loops: Animation.Infinite
                            PropertyAnimation {
                                from: Qt.vector3d(
                                    -(modelData.distance || 3.0)/2 * Math.cos((modelData.rotation || 0) * Math.PI/180),
                                    0,
                                    -(modelData.distance || 3.0)/2 * Math.sin((modelData.rotation || 0) * Math.PI/180)
                                )
                                to: Qt.vector3d(
                                    (modelData.distance || 3.0)/2 * Math.cos((modelData.rotation || 0) * Math.PI/180),
                                    0,
                                    (modelData.distance || 3.0)/2 * Math.sin((modelData.rotation || 0) * Math.PI/180)
                                )
                                duration: 3000 / (modelData.speed || 1.5)
                            }
                            PropertyAnimation {
                                from: Qt.vector3d(
                                    (modelData.distance || 3.0)/2 * Math.cos((modelData.rotation || 0) * Math.PI/180),
                                    0,
                                    (modelData.distance || 3.0)/2 * Math.sin((modelData.rotation || 0) * Math.PI/180)
                                )
                                to: Qt.vector3d(
                                    -(modelData.distance || 3.0)/2 * Math.cos((modelData.rotation || 0) * Math.PI/180),
                                    0,
                                    -(modelData.distance || 3.0)/2 * Math.sin((modelData.rotation || 0) * Math.PI/180)
                                )
                                duration: 3000 / (modelData.speed || 1.5)
                            }
                        }

                        // ── Animazione Drop Turner ──
                        SequentialAnimation on eulerRotation.x {
                            running: modelData.mat === "target"
                                    && modelData.fall_time !== undefined
                            loops: Animation.Infinite
                            PauseAnimation { duration: 2000 }
                            NumberAnimation {
                                from: 0
                                to: 90
                                duration: (modelData.fall_time || 0.5) * 1000
                                easing.type: Easing.InQuad
                            }
                            PauseAnimation { duration: 1500 }
                            NumberAnimation {
                                from: 90
                                to: 0
                                duration: 800
                                easing.type: Easing.OutQuad
                            }
                        }
                    }
                }
            }

            /* ─── INDICATORE POSIZIONE FP SUL PAVIMENTO ─── */
            Model {
                id: fpIndicator
                source: "#Sphere"
                visible: root.fpMode
                position: Qt.vector3d(fpCamera.position.x, 0.05, fpCamera.position.z)
                scale: Qt.vector3d(0.15, 0.05, 0.15)
                materials: [ PrincipledMaterial {
                    baseColor: "#3b82f6"
                    roughness: 0.5
                    opacity: 0.6
                }]
            }
        }

        /* ─── CONTROLLI MOUSE — MODALITÀ ORBITALE ─── */
        MouseArea {
            id: orbitMouse
            anchors.fill: parent
            enabled: !root.fpMode
            hoverEnabled: true
            property real lastX: 0
            property real lastY: 0
            property bool dragging: false
            property int dragButton: 0

            onPressed: (mouse) => {
                if (mouse.y < 48) return;
                dragging = true;
                lastX = mouse.x;
                lastY = mouse.y;
                dragButton = mouse.button;
                cursorShape = Qt.DragMoveCursor;
            }
            onReleased: {
                dragging = false;
                dragButton = 0;
                cursorShape = Qt.ArrowCursor;
            }
            onPositionChanged: (mouse) => {
                if (!dragging) return;
                var dx = mouse.x - lastX;
                var dy = mouse.y - lastY;
                lastX = mouse.x;
                lastY = mouse.y;
                var sens = 0.4;

                if (dragButton === Qt.LeftButton) {
                    var ry = orbitCamera.eulerRotation.y;
                    var rx = orbitCamera.eulerRotation.x;
                    orbitCamera.eulerRotation.y = ry - dx * sens;
                    orbitCamera.eulerRotation.x = Math.max(-89, Math.min(89, rx + dy * sens));
                } else {
                    var panSens = 0.04;
                    var angleRad = orbitCamera.eulerRotation.y * Math.PI / 180;
                    var forwardX = -Math.sin(angleRad);
                    var forwardZ = -Math.cos(angleRad);
                    var rightX = -Math.sin(angleRad + Math.PI/2);
                    var rightZ = -Math.cos(angleRad + Math.PI/2);
                    orbitOrigin.position.x += (-dx * rightX + dy * forwardX) * panSens;
                    orbitOrigin.position.z += (-dx * rightZ + dy * forwardZ) * panSens;
                }
            }
            onWheel: (wheel) => {
                var dir = orbitOrigin.position.minus(orbitCamera.position).normalized();
                var dist = wheel.angleDelta.y > 0 ? 1.5 : -1.5;
                orbitCamera.position = orbitCamera.position.plus(dir.times(dist));
            }
        }

        /* ─── CONTROLLI MOUSE — MODALITÀ FP ─── */
        MouseArea {
            id: fpMouse
            anchors.fill: parent
            enabled: root.fpMode
            hoverEnabled: true
            property real lastX: 0
            property real lastY: 0
            property bool dragging: false

            onPressed: (mouse) => {
                if (mouse.y < 48) return;
                dragging = true;
                lastX = mouse.x;
                lastY = mouse.y;
                cursorShape = Qt.BlankCursor;
            }
            onReleased: {
                dragging = false;
                cursorShape = Qt.ArrowCursor;
            }
            onPositionChanged: (mouse) => {
                if (!dragging || !root.fpMode) return;
                var dx = mouse.x - lastX;
                var dy = mouse.y - lastY;
                lastX = mouse.x;
                lastY = mouse.y;
                keyInput.yaw -= dx * 0.3;
                keyInput.pitch = root.clamp(keyInput.pitch - dy * 0.3, -80, 80);
                fpCamera.eulerRotation.y = keyInput.yaw;
                fpCamera.eulerRotation.x = keyInput.pitch;
            }
        }
    }

    /* ═══════════════════════════════════════════════════
       OVERLAY UI
       ═══════════════════════════════════════════════════ */

    // Pannello superiore sinistro
    Row {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: 12
        spacing: 6
        z: 10

        Button {
            text: root.fpMode ? "🎥 Orbita" : "🚶 Prima persona"
            flat: true
            contentItem: Text {
                text: parent.text
                color: "#ffffff"
                font.pixelSize: 13
                font.bold: true
            }
            background: Rectangle {
                color: root.fpMode ? "#2563eb" : "#475569"
                radius: 6
                border.color: root.fpMode ? "#60a5fa" : "#64748b"
                border.width: 1
            }
            onClicked: {
                if (root.fpMode) {
                    // Passa a orbitale: centra origine su posizione FP
                    orbitOrigin.position.x = fpCamera.position.x;
                    orbitOrigin.position.z = fpCamera.position.z;
                    // Posiziona camera orbitale sopra la posizione FP
                    orbitCamera.position.x = fpCamera.position.x;
                    orbitCamera.position.z = fpCamera.position.z + 10;
                    orbitCamera.eulerRotation = Qt.vector3d(-35, 0, 0);
                } else {
                    // Passa a FP: usa posizione orbitale corrente
                    // Proietta la posizione orbitale al livello giocatore
                    var angleRad = orbitCamera.eulerRotation.y * Math.PI / 180;
                    var dist = orbitCamera.position.minus(orbitOrigin.position).length();
                    // Posiziona FP dove sta guardando l'orbita
                    fpCamera.position.x = orbitCamera.position.x;
                    fpCamera.position.z = orbitCamera.position.z;
                    fpCamera.position.y = root.playerHeight;
                    keyInput.yaw = orbitCamera.eulerRotation.y;
                    keyInput.pitch = orbitCamera.eulerRotation.x;
                    fpCamera.eulerRotation.y = keyInput.yaw;
                    fpCamera.eulerRotation.x = keyInput.pitch;
                }
                root.fpMode = !root.fpMode;
                keyInput.forceActiveFocus();
            }
        }

        Button {
            text: "🏠 Resetta"
            flat: true
            contentItem: Text {
                text: parent.text
                color: "#ffffff"
                font.pixelSize: 13
            }
            background: Rectangle {
                color: "#334155"
                radius: 6
                border.color: "#475569"
                border.width: 1
            }
            onClicked: root.resetOrbitCamera()
        }

        Item { width: 12; height: 1 }

        Label {
            text: root.fpMode
                  ? "WASD muovi | Shift sprint | Mouse guarda | Spazio salta"
                  : "WASD/frecce pan | Q/E zoom | Home reset | Sinistro orbita | Destro/medio pan"
            color: "#94a3b8"
            font.pixelSize: 12
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    // Pannello superiore destro
    Column {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: 12
        spacing: 6
        z: 10

        Button {
            text: "⛶ Fullscreen"
            flat: true
            contentItem: Text {
                text: parent.text
                color: "#ffffff"
                font.pixelSize: 13
            }
            background: Rectangle {
                color: "#1e40af"
                radius: 6
                border.color: "#3b82f6"
                border.width: 1
            }
            onClicked: root.requestFullscreen()
        }
    }

    // Mini-mappa in basso a destra
    Rectangle {
        id: minimap
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.margins: 12
        width: 140
        height: 105
        radius: 8
        color: "#0f172a"
        opacity: 0.8
        z: 10

        readonly property real scaleX: width / (floorWidth || 20)
        readonly property real scaleY: height / (floorDepth || 15)
        readonly property real camX: root.fpMode ? fpCamera.position.x : orbitCamera.position.x
        readonly property real camZ: root.fpMode ? fpCamera.position.z : orbitCamera.position.z

        // Sfondo griglia
        Canvas {
            anchors.fill: parent
            anchors.margins: 4
            onPaint: {
                var ctx = getContext("2d");
                ctx.clearRect(0, 0, width, height);
                ctx.strokeStyle = "#334155";
                ctx.lineWidth = 0.5;
                var sw = width / (minimap.scaleX || 1);
                var sh = height / (minimap.scaleY || 1);
                for (var i = 0; i <= sw; i++) {
                    ctx.beginPath();
                    ctx.moveTo(i * minimap.scaleX, 0);
                    ctx.lineTo(i * minimap.scaleX, height);
                    ctx.stroke();
                }
                for (var j = 0; j <= sh; j++) {
                    ctx.beginPath();
                    ctx.moveTo(0, j * minimap.scaleY);
                    ctx.lineTo(width, j * minimap.scaleY);
                    ctx.stroke();
                }
            }
        }

        // Puntatore posizione
        Rectangle {
            x: minimap.camX * minimap.scaleX - 3
            y: (floorDepth - minimap.camZ) * minimap.scaleY - 3
            width: 6
            height: 6
            radius: 3
            color: root.fpMode ? "#3b82f6" : "#f59e0b"
        }

        Label {
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.margins: 4
            text: "📍 " + (root.fpMode
                ? fpCamera.position.x.toFixed(1) + ", " + fpCamera.position.z.toFixed(1)
                : "")
            color: "#94a3b8"
            font.pixelSize: 9
        }
    }

    // Info stato
    Label {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.margins: 12
        text: "Qt Quick 3D — " + (root.fpMode ? "Modalità First-Person" : "Modalità Orbitale")
              + (root.fpMode ? ("  |  Pos: " + fpCamera.position.x.toFixed(1) + ", " + fpCamera.position.z.toFixed(1)) : "")
        color: "#64748b"
        font.pixelSize: 11
        z: 10
    }
}
