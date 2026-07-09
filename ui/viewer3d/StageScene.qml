import QtQuick
import QtQuick3D
import QtQuick3D.Helpers
import QtQuick.Controls

Rectangle {
    id: root
    color: "#1e293b"

    property real floorWidth: stageWidth
    property real floorDepth: stageDepth
    property bool fpMode: false
    property real panSpeed: 6.0
    property real zoomSpeed: 2.0

    // Resetta la camera orbitale alla posizione iniziale
    function resetOrbitCamera() {
        orbitCamera.position = Qt.vector3d(floorWidth / 2, 12, floorDepth + 8);
        orbitCamera.eulerRotation = Qt.vector3d(-35, 0, 0);
        orbitOrigin.position = Qt.vector3d(floorWidth / 2, 0, floorDepth / 2);
    }

    // Segnali per fullscreen
    signal requestFullscreen()

    // Item invisibile che cattura i tasti per entrambe le modalità
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
        property real yaw: 0
        property real pitch: 0

        function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

        Keys.onPressed: (event) => {
            if (!root.fpMode) {
                // Modalità orbitale: WASD/arrows pan, Q/E zoom, Home reset
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
                // Modalità FP
                switch(event.key) {
                    case Qt.Key_W: moveForward = true; break;
                    case Qt.Key_S: moveBack = true; break;
                    case Qt.Key_A: moveLeft = true; break;
                    case Qt.Key_D: moveRight = true; break;
                    case Qt.Key_Shift: sprint = true; break;
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
                }
            }
        }

        // Timer movimento camera orbitale (WASD/arrows pan)
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

        // Timer movimento camera FP (WASD)
        Timer {
            interval: 16
            running: root.fpMode
            repeat: true
            onTriggered: {
                var speed = 3.0 * (keyInput.sprint ? 2.0 : 1.0) * (interval / 1000);
                var ry = fpCamera.eulerRotation.y * Math.PI / 180;
                var fx = -Math.sin(ry);
                var fz = -Math.cos(ry);
                var rx = -Math.sin(ry + Math.PI/2);
                var rz = -Math.cos(ry + Math.PI/2);

                var dx = 0, dz = 0;
                if (keyInput.moveForward) { dx += fx * speed; dz += fz * speed; }
                if (keyInput.moveBack)    { dx -= fx * speed; dz -= fz * speed; }
                if (keyInput.moveLeft)    { dx += rx * speed; dz += rz * speed; }
                if (keyInput.moveRight)   { dx -= rx * speed; dz -= rz * speed; }

                fpCamera.position.x += dx;
                fpCamera.position.z += dz;
            }
        }
    }

    View3D {
        id: view3d
        anchors.fill: parent
        camera: root.fpMode ? fpCamera : orbitCamera
        environment: SceneEnvironment {
            clearColor: "#1e293b"
            backgroundMode: SceneEnvironment.Color
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
        }

        Node {
            id: scene

            DirectionalLight {
                id: sun
                color: "#ffffff"
                ambientColor: "#404040"
                brightness: 1.2
                eulerRotation.x: -45
                eulerRotation.y: 30
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
                position: Qt.vector3d(2, 1.7, 2)
                eulerRotation: Qt.vector3d(0, 0, 0)
                clipNear: 0.1
                clipFar: 1000
            }

            // Pavimento
            Model {
                source: "#Cube"
                position: Qt.vector3d(floorWidth / 2, -0.05, floorDepth / 2)
                scale: Qt.vector3d(floorWidth, 0.1, floorDepth)
                materials: [ PrincipledMaterial {
                    baseColor: "#334155"
                    roughness: 0.9
                }]
            }

            // Griglia pavimento
            Repeater3D {
                model: Math.floor(floorWidth) + 1
                Model {
                    source: "#Cube"
                    position: Qt.vector3d(index, 0.001, floorDepth / 2)
                    scale: Qt.vector3d(0.02, 0.02, floorDepth)
                    materials: [ PrincipledMaterial { baseColor: "#475569"; roughness: 1.0 } ]
                }
            }
            Repeater3D {
                model: Math.floor(floorDepth) + 1
                Model {
                    source: "#Cube"
                    position: Qt.vector3d(floorWidth / 2, 0.001, index)
                    scale: Qt.vector3d(floorWidth, 0.02, 0.02)
                    materials: [ PrincipledMaterial { baseColor: "#475569"; roughness: 1.0 } ]
                }
            }

            // ─── PARAPALLE DI FONDO (BACKSTOP) ───
            // Parete fondale alta 4m, colore terra
            Model {
                source: "#Cube"
                position: Qt.vector3d(floorWidth / 2, 2.5, floorDepth + 0.15)
                scale: Qt.vector3d(floorWidth + 2.0, 5.0, 0.3)
                materials: [ PrincipledMaterial {
                    baseColor: "#5c3a1e"
                    roughness: 0.95
                }]
            }

            // Parapalle: ali laterali (bersaglio sicurezza)
            Model {
                source: "#Cube"
                position: Qt.vector3d(-0.15, 2.5, floorDepth / 2)
                scale: Qt.vector3d(0.3, 5.0, floorDepth)
                materials: [ PrincipledMaterial {
                    baseColor: "#5c3a1e"
                    roughness: 0.95
                }]
            }
            Model {
                source: "#Cube"
                position: Qt.vector3d(floorWidth + 0.15, 2.5, floorDepth / 2)
                scale: Qt.vector3d(0.3, 5.0, floorDepth)
                materials: [ PrincipledMaterial {
                    baseColor: "#5c3a1e"
                    roughness: 0.95
                }]
            }

            // ─── ZONA PARTENZA TIRATORE ───
            // Rettangolo colorato sul pavimento all'ingresso
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

            // ─── FRECCE DIREZIONALI (semplici indicatori) ───
            // Indicatore UP-RANGE (verso tiratore)
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
            // Indicatore DOWN-RANGE (verso parapalle)
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

            // ─── OGGETTI STAGE (da Python) ───
            Repeater3D {
                model: stage3dModel.objects
                Node {
                    id: objNode
                    position: Qt.vector3d(modelData.x, modelData.y, modelData.z)

                    Model {
                        // #Cube per tutti: #Rectangle è 2D monofacciale e scompare
                        // quando ruotato. #Cube con scaleZ sottile (0.02) dà lo stesso
                        // effetto cartoncino ma visibile da ogni angolazione.
                        source: "#Cube"
                        scale: Qt.vector3d(modelData.scaleX, modelData.scaleY, modelData.scaleZ)
                        eulerRotation.y: modelData.rotation
                        materials: [ PrincipledMaterial {
                            baseColor: modelData.color
                            roughness: 0.6
                        }]

                        // Animazione Swinger: oscillazione rotazione Y
                        SequentialAnimation on eulerRotation.y {
                            running: modelData.type === "swinger"
                            loops: Animation.Infinite
                            RotationAnimation {
                                from: modelData.rotation - (modelData.amplitude || 45)
                                to: modelData.rotation + (modelData.amplitude || 45)
                                duration: 2000 / (modelData.speed || 1.0)
                            }
                            RotationAnimation {
                                from: modelData.rotation + (modelData.amplitude || 45)
                                to: modelData.rotation - (modelData.amplitude || 45)
                                duration: 2000 / (modelData.speed || 1.0)
                            }
                        }

                        // Animazione Mover: traslazione oscillante lungo l'asse di rotazione
                        // Calcola spostamento in coordinate locali usando l'angolo di rotazione
                        SequentialAnimation on position {
                            running: modelData.type === "mover"
                            loops: Animation.Infinite
                            PropertyAnimation {
                                from: Qt.vector3d(
                                    -(modelData.distance || 3.0)/2 * Math.cos(modelData.rotation * Math.PI/180),
                                    0,
                                    -(modelData.distance || 3.0)/2 * Math.sin(modelData.rotation * Math.PI/180)
                                )
                                to: Qt.vector3d(
                                    (modelData.distance || 3.0)/2 * Math.cos(modelData.rotation * Math.PI/180),
                                    0,
                                    (modelData.distance || 3.0)/2 * Math.sin(modelData.rotation * Math.PI/180)
                                )
                                duration: 3000 / (modelData.speed || 1.5)
                            }
                            PropertyAnimation {
                                from: Qt.vector3d(
                                    (modelData.distance || 3.0)/2 * Math.cos(modelData.rotation * Math.PI/180),
                                    0,
                                    (modelData.distance || 3.0)/2 * Math.sin(modelData.rotation * Math.PI/180)
                                )
                                to: Qt.vector3d(
                                    -(modelData.distance || 3.0)/2 * Math.cos(modelData.rotation * Math.PI/180),
                                    0,
                                    -(modelData.distance || 3.0)/2 * Math.sin(modelData.rotation * Math.PI/180)
                                )
                                duration: 3000 / (modelData.speed || 1.5)
                            }
                        }

                        // Animazione Drop Turner: rotazione X da verticale a orizzontale
                        SequentialAnimation on eulerRotation.x {
                            running: modelData.type === "drop_turner"
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
        }

        // ─── CONTROLLI MOUSE MODALITÀ ORBITALE ───
        MouseArea {
            id: orbitMouse
            anchors.fill: parent
            enabled: !root.fpMode
            hoverEnabled: true
            property real lastX: 0
            property real lastY: 0
            property bool dragging: false
            property int dragButton: 0  // 1=left, 2=right, 4=middle

            onPressed: (mouse) => {
                // Non consumare click sui pulsanti UI (controlli sopra)
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

                // Sensibilità
                var sens = 0.4;

                if (dragButton === Qt.LeftButton) {
                    // → ORBITA: ruota telecamera attorno a orbitOrigin
                    var ry = orbitCamera.eulerRotation.y;
                    var rx = orbitCamera.eulerRotation.x;
                    orbitCamera.eulerRotation.y = ry - dx * sens;
                    orbitCamera.eulerRotation.x = Math.max(-89, Math.min(89, rx + dy * sens));
                } else {
                    // → PAN (tasto destro O medio): sposta orbitOrigin
                    var panSens = 0.04;
                    // Calcola direzioni locali
                    var angleRad = orbitCamera.eulerRotation.y * Math.PI / 180;
                    var forwardX = -Math.sin(angleRad);
                    var forwardZ = -Math.cos(angleRad);
                    var rightX = -Math.sin(angleRad + Math.PI/2);
                    var rightZ = -Math.cos(angleRad + Math.PI/2);
                    // Sposta origine nella direzione del drag
                    orbitOrigin.position.x += (-dx * rightX + dy * forwardX) * panSens;
                    orbitOrigin.position.z += (-dx * rightZ + dy * forwardZ) * panSens;
                }
            }
            onWheel: (wheel) => {
                // → ZOOM
                var dir = orbitOrigin.position.minus(orbitCamera.position).normalized();
                var dist = wheel.angleDelta.y > 0 ? 1.5 : -1.5;
                orbitCamera.position = orbitCamera.position.plus(dir.times(dist));
            }
        }

        // ─── CONTROLLI MOUSE MODALITÀ FP ───
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
            }
            onReleased: { dragging = false; }
            onPositionChanged: (mouse) => {
                if (!dragging || !root.fpMode) return;
                var dx = mouse.x - lastX;
                var dy = mouse.y - lastY;
                lastX = mouse.x;
                lastY = mouse.y;
                keyInput.yaw -= dx * 0.3;
                keyInput.pitch = keyInput.clamp(keyInput.pitch - dy * 0.3, -80, 80);
                fpCamera.eulerRotation.y = keyInput.yaw;
                fpCamera.eulerRotation.x = keyInput.pitch;
            }
        }
    }

    // Pannello di controllo superiore
    Row {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: 12
        spacing: 6

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

        // Spacer
        Item { width: 12; height: 1 }

        Label {
            text: root.fpMode
                  ? "WASD muovi | Shift sprint | Mouse guarda"
                  : "WASD/frecce pan | Q/E zoom | Home reset | Sinistro orbita | Destro/medio pan"
            color: "#94a3b8"
            font.pixelSize: 12
            anchors.verticalCenter: parent.verticalCenter
        }

    }

    // Pannello di controllo superiore destro
    Column {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: 12
        spacing: 6

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

    // Info stato
    Label {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.margins: 12
        text: "Qt Quick 3D — " + (root.fpMode ? "Modalità First-Person" : "Modalità Orbitale")
        color: "#64748b"
        font.pixelSize: 11
    }
}
