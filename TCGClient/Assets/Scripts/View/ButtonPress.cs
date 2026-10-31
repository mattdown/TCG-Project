using DG.Tweening;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Tcg.View
{
    /// <summary>
    /// The pressed state of a <see cref="Ui.Button"/>: while held it sinks a little and its glass
    /// lights up in the rim's colour. The colours are read on each press, so a retint still shows.
    /// </summary>
    [RequireComponent(typeof(Button))]
    public class ButtonPress : MonoBehaviour, IPointerDownHandler, IPointerUpHandler, IPointerExitHandler
    {
        const float PressedScale = 0.95f;
        Button _button;
        Image _wash, _rim;
        Color _washColour, _rimColour;
        bool _pressed;

        void Awake()
        {
            _button = GetComponent<Button>();
            _wash = transform.Find("Wash").GetComponent<Image>();
            _rim = transform.Find("Rim").GetComponent<Image>();
        }

        public void OnPointerDown(PointerEventData e)
        {
            if (_pressed || !_button.IsInteractable() || e.button != PointerEventData.InputButton.Left) return;
            _pressed = true;
            _washColour = _wash.color;
            _rimColour = _rim.color;
            _wash.color = _rimColour.WithAlpha(0.18f);
            _rim.color = _rimColour.WithAlpha(1f);
            transform.DOKill();
            transform.DOScale(PressedScale, 0.06f).SetEase(Ease.OutQuad);
        }

        public void OnPointerUp(PointerEventData e) => Release();

        public void OnPointerExit(PointerEventData e) => Release();

        void OnDisable() => Release();

        void Release()
        {
            if (!_pressed) return;
            _pressed = false;
            _wash.color = _washColour;
            _rim.color = _rimColour;
            transform.DOKill();
            transform.DOScale(1f, 0.1f).SetEase(Ease.OutBack);
        }
    }
}
