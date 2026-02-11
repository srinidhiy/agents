import gradio as gr
from sidekick import Sidekick


async def setup():
    sidekick = Sidekick()
    await sidekick.setup()
    return sidekick


async def process_message(
    sidekick,
    message,
    success_criteria,
    history,
    gift_mode,
    budget_min,
    budget_max,
    recipient_interests,
    occasion,
):
    # Parse budget values
    budget_min_val = None
    budget_max_val = None
    
    if gift_mode:
        try:
            if budget_min and str(budget_min).strip():
                budget_min_val = float(budget_min)
        except (ValueError, TypeError):
            pass
        
        try:
            if budget_max and str(budget_max).strip():
                budget_max_val = float(budget_max)
        except (ValueError, TypeError):
            pass
    
    results = await sidekick.run_superstep(
        message=message,
        success_criteria=success_criteria,
        history=history,
        gift_mode=gift_mode,
        budget_min=budget_min_val,
        budget_max=budget_max_val,
        recipient_interests=recipient_interests if gift_mode else None,
        occasion=occasion if gift_mode else None,
    )
    return results, sidekick


async def reset():
    new_sidekick = Sidekick()
    await new_sidekick.setup()
    return "", "", None, new_sidekick, False, None, None, "", "Birthday"


def free_resources(sidekick):
    print("Cleaning up")
    try:
        if sidekick:
            sidekick.cleanup()
    except Exception as e:
        print(f"Exception during cleanup: {e}")


def toggle_gift_mode(enabled):
    """Show/hide gift mode fields based on toggle"""
    return gr.update(visible=enabled)


# Custom CSS for better styling
custom_css = """
.gift-mode-section {
    border: 2px solid #10b981;
    border-radius: 8px;
    padding: 12px;
    margin-top: 8px;
    background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
}
.gift-mode-section.dark {
    background: linear-gradient(135deg, #064e3b 0%, #065f46 100%);
}
"""

with gr.Blocks(
    title="Sidekick Shopping Assistant",
    theme=gr.themes.Default(primary_hue="emerald"),
    css=custom_css,
) as ui:
    gr.Markdown("## 🛒 Sidekick Shopping Assistant")
    gr.Markdown("*Your AI-powered personal shopper - finds products, compares prices, and adds to cart*")
    
    sidekick = gr.State(delete_callback=free_resources)

    with gr.Row():
        chatbot = gr.Chatbot(label="Sidekick", height=400, type="messages")
    
    # Main request section
    with gr.Group():
        with gr.Row():
            message = gr.Textbox(
                show_label=False,
                placeholder="What would you like to shop for? (e.g., 'Find me wireless headphones under $100')",
                lines=2,
            )
        with gr.Row():
            success_criteria = gr.Textbox(
                show_label=False,
                placeholder="Success criteria (e.g., 'Find at least 3 options with good reviews')",
            )
    
    # Gift Mode Section
    with gr.Accordion("🎁 Gift Finding Mode", open=False) as gift_accordion:
        gift_mode = gr.Checkbox(
            label="Enable Gift Mode",
            value=False,
            info="Get personalized gift recommendations based on recipient's interests and your budget",
        )
        
        with gr.Column(visible=False) as gift_fields:
            with gr.Row():
                budget_min = gr.Number(
                    label="Min Budget ($)",
                    value=None,
                    minimum=0,
                    precision=2,
                    info="Minimum price",
                )
                budget_max = gr.Number(
                    label="Max Budget ($)",
                    value=None,
                    minimum=0,
                    precision=2,
                    info="Maximum price",
                )
            
            recipient_interests = gr.Textbox(
                label="Recipient's Interests",
                placeholder="e.g., gaming, cooking, fitness, technology, books, music",
                info="What does the gift recipient enjoy?",
            )
            
            occasion = gr.Dropdown(
                label="Occasion",
                choices=[
                    "Birthday",
                    "Christmas",
                    "Anniversary",
                    "Valentine's Day",
                    "Mother's Day",
                    "Father's Day",
                    "Graduation",
                    "Wedding",
                    "Housewarming",
                    "Thank You",
                    "Just Because",
                    "Other",
                ],
                value="Birthday",
                info="What's the occasion for the gift?",
            )
        
        # Toggle gift fields visibility
        gift_mode.change(
            fn=toggle_gift_mode,
            inputs=[gift_mode],
            outputs=[gift_fields],
        )
    
    # Action buttons
    with gr.Row():
        reset_button = gr.Button("🔄 Reset", variant="stop")
        go_button = gr.Button("🛒 Shop!", variant="primary", size="lg")

    # Tips section
    with gr.Accordion("💡 Tips", open=False):
        gr.Markdown("""
        **Shopping Tips:**
        - Be specific about what you're looking for (brand, features, price range)
        - The assistant can search Amazon, Target, and Google Shopping
        - You can ask it to compare products before deciding
        - For adding to cart, make sure you're logged into the shopping site in the browser window
        
        **Gift Mode Tips:**
        - Enable Gift Mode for personalized recommendations
        - Set a budget range to filter results
        - List multiple interests for better suggestions
        - The assistant will explain why each gift is a good match
        """)

    # Event handlers
    ui.load(setup, [], [sidekick])
    
    # All input fields for process_message
    input_fields = [
        sidekick,
        message,
        success_criteria,
        chatbot,
        gift_mode,
        budget_min,
        budget_max,
        recipient_interests,
        occasion,
    ]
    
    message.submit(process_message, input_fields, [chatbot, sidekick])
    success_criteria.submit(process_message, input_fields, [chatbot, sidekick])
    go_button.click(process_message, input_fields, [chatbot, sidekick])
    
    # Reset clears all fields
    reset_button.click(
        reset,
        [],
        [message, success_criteria, chatbot, sidekick, gift_mode, budget_min, budget_max, recipient_interests, occasion],
    )


ui.launch(inbrowser=True)
