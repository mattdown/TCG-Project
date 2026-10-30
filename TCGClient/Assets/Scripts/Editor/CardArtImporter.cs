using UnityEditor;
using UnityEngine;

/// <summary>
/// Import settings for generated card art (Resources/CardArt, made by Tools/card_art), applied
/// as each image arrives, so new art needs no rebuild: sprites that CardView loads by name,
/// mipmapped because a 640x800 image is shown much smaller on the board.
/// </summary>
public class CardArtImporter : AssetPostprocessor
{
    const string Folder = "Assets/Resources/CardArt/";

    void OnPreprocessTexture()
    {
        if (!assetPath.StartsWith(Folder)) return;
        var ti = (TextureImporter)assetImporter;
        ti.textureType = TextureImporterType.Sprite;
        ti.spriteImportMode = SpriteImportMode.Single;
        ti.mipmapEnabled = true;
        ti.maxTextureSize = 1024;
        ti.textureCompression = TextureImporterCompression.CompressedHQ;
        ti.filterMode = FilterMode.Trilinear;
        ti.wrapMode = TextureWrapMode.Clamp;
        var settings = new TextureImporterSettings();
        ti.ReadTextureSettings(settings);
        settings.spriteMeshType = SpriteMeshType.FullRect;
        ti.SetTextureSettings(settings);
    }
}
