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

    // Item invisibile che cattura i tasti per la modalità FP
    Item {
        id: fpInput
        focus: root.fpMode
        anchors.fill: parent  // occupa tutto per catturare focus correttamente

        property bool moveForward: false
        property bool moveBack: false
        property bool moveLeft: false
        property bool moveRight: false
        property bool sprint: false
        property real yaw: 0
        property real pitch: 0

        function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

        Keys.onPressed: (event) => {
            switch(event.key) {
                case Qt.Key_W: moveForward = true; break;
                case Qt.Key_S: moveBack = true; break;
                case Qt.Key_A: moveLeft = true; break;
                case Qt.Key_D: moveRight = true; break;
                case Qt.Key_Shift: sprint = true; break;
            }
        }
        Keys.onReleased: (event) => {
            switch(event.key) {
                case Qt.Key_W: moveForward = false; break;
                case Qt.Key_S: moveBack = false; break;
                case Qt.Key_A: moveLeft = false; break;
                case Qt.Key_D: moveRight = false; break;
                case Qt.Key_Shift: sprint = false; break;
            }
        }

        Timer {
            interval: 16
            running: root.fpMode
            repeat: true
            onTriggered: {
                var speed = 3.0 * (fpInput.sprint ? 2.0 : 1.0) * (interval / 1000);
                var ry = fpCamera.eulerRotation.y * Math.PI / 180;
                var fx = -Math.sin(ry);
                var fz = -Math.cos(ry);
                var rx = -Math.sin(ry + Math.PI/2);
                var rz = -Math.cos(ry + Math.PI/2);

                var dx = 0, dz = 0;
                if (fpInput.moveForward) { dx += fx * speed; dz += fz * speed; }
                if (fpInput.moveBack)    { dx -= fx * speed; dz -= fz * speed; }
                if (fpInput.moveLeft)    { dx += rx * speed; dz += rz * speed; }
                if (fpInput.moveRight)   { dx -= rx * speed; dz -= rz * speed; }

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

            // Oggetti stage esposti da Python
            Repeater3D {
                model: stage3dModel.objects
                Node {
                    id: objNode
                    position: Qt.vector3d(modelData.x, modelData.y, modelData.z)

                    Model {
                        source: (modelData.type === "target" || modelData.type === "noshoot" ||
                                modelData.type === "swinger" || modelData.type === "drop_turner" ||
                                modelData.type === "mover") ? "#Rectangle" : "#Cube"
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

                        // Animazione Mover: traslazione oscillante
                        SequentialAnimation on position.x {
                            running: modelData.type === "mover"
                            loops: Animation.Infinite
                            NumberAnimation {
                                from: modelData.x - (modelData.distance || 3.0)/2
                                to: modelData.x + (modelData.distance || 3.0)/2
                                duration: 3000 / (modelData.speed || 1.5)
                            }
                            NumberAnimation {
                                from: modelData.x + (modelData.distance || 3.0)/2
                                to: modelData.x - (modelData.distance || 3.0)/2
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

        // Controlli camera
        OrbitCameraController {
            id: orbitController
            camera: orbitCamera
            enabled: !root.fpMode
            origin: orbitOrigin
            xSpeed: 0.5
            ySpeed: 0.5
        }

        // Mouse look per first-person
        MouseArea {
            anchors.fill: parent
            enabled: root.fpMode
            hoverEnabled: true
            property real lastX: 0
            property real lastY: 0
            property bool dragging: false

            onPressed: (mouse) => {
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
                fpInput.yaw -= dx * 0.3;
                fpInput.pitch = fpInput.clamp(fpInput.pitch - dy * 0.3, -80, 80);
                fpCamera.eulerRotation.y = fpInput.yaw;
                fpCamera.eulerRotation.x = fpInput.pitch;
            }
        }
    }

    // Toggle camera mode
    Row {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: 12
        spacing: 8

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
            }
            onClicked: {
                root.fpMode = !root.fpMode;
                if (root.fpMode) fpInput.forceActiveFocus();
            }
        }

        Label {
            text: root.fpMode
                  ? "WASD muovi | Shift sprint | Mouse guarda | Click per catturare mouse"
                  : "Drag ruota | Rotella zoom | Shift+drag pan"
            color: "#94a3b8"
            font.pixelSize: 12
            anchors.verticalCenter: parent.verticalCenter
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
