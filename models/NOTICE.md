# Modèles et droits

- `yolox_s.onnx` et `yolox_nano.onnx` proviennent de la publication 0.1.1rc0 de Megvii-BaseDetection. Les modèles ont été utilisés sans modification des poids. Le code SallePilot applique le prétraitement et le décodage ONNX nécessaires pour isoler la classe personne. La licence Apache 2.0 est fournie dans `YOLOX-LICENSE.txt`. [Dépôt des auteurs](https://github.com/Megvii-BaseDetection/YOLOX) · [Liens des modèles ONNX](https://github.com/Megvii-BaseDetection/YOLOX/tree/main/demo/ONNXRuntime)
- `experimental-crop-v2.npz` est le classificateur entraîné pour cette étude. Données d’entraînement : *The Oldest Chinese Restaurant in Singapore – Spring Court*, SETHLUI.com, CC BY 3.0, et *30-Second Chair Stand Test*, CDC, indiqué comme domaine public aux États-Unis. Modifications : retrait de l’audio, conversion en 640 pixels de large, recadrage, annotations et entraînement. Ce modèle est fourni pour reproduction et reste désactivé par défaut. [Manifeste des sources](../evaluation/sources.json)
- Le modèle de pose OpenCV Zoo a été évalué séparément et ne fait pas partie du moteur livré. Son script d’essai attend l’export ONNX officiel. [OpenCV Zoo MediaPipe Pose](https://github.com/opencv/opencv_zoo/tree/main/models/pose_estimation_mediapipe)

| Fichier | SHA-256 |
|---|---|
| `yolox_s.onnx` | `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063` |
| `yolox_nano.onnx` | `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d` |
| `experimental-crop-v2.npz` | `9c2bfd60fabd89406a26d88921997cc8937ccfd18db6289735893c1d9ae85a23` |
