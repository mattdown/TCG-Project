using UnityEngine;
using UnityEngine.EventSystems;

namespace Tcg.View
{
    /// <summary>Receives a card's pointer events. Taps and drags both go to the board.</summary>
    public interface ICardInputHandler
    {
        void OnCardTap(CardView card);
        bool OnCardDragStart(CardView card, PointerEventData e);
        void OnCardDrag(CardView card, PointerEventData e);
        void OnCardDragEnd(CardView card, PointerEventData e);
    }

    /// <summary>
    /// Forwards pointer events from a card to its handler. A press that never moves past the event
    /// system's drag threshold arrives as a click, so a short drag counts as a tap.
    /// </summary>
    [RequireComponent(typeof(CardView))]
    public class CardInput : MonoBehaviour, IPointerClickHandler, IBeginDragHandler, IDragHandler, IEndDragHandler
    {
        public ICardInputHandler Handler;
        CardView _card;
        bool _dragging;

        void Awake() => _card = GetComponent<CardView>();

        public void OnPointerClick(PointerEventData e)
        {
            if (!e.dragging) Handler?.OnCardTap(_card);
        }

        public void OnBeginDrag(PointerEventData e)
        {
            _dragging = Handler != null && Handler.OnCardDragStart(_card, e);
            if (!_dragging) e.pointerDrag = null;
        }

        public void OnDrag(PointerEventData e)
        {
            if (_dragging) Handler.OnCardDrag(_card, e);
        }

        public void OnEndDrag(PointerEventData e)
        {
            if (!_dragging) return;
            _dragging = false;
            Handler.OnCardDragEnd(_card, e);
        }
    }
}
