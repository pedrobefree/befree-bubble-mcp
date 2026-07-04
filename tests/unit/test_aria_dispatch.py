from bubble_mcp.aria_dispatch import _method_kwargs


def test_method_kwargs_maps_public_schema_aliases_to_aria_runtime_args() -> None:
    def create_data_field(
        data_type_key: str,
        field_name: str,
        field_type: str,
        dry_run: bool = False,
    ) -> bool:
        return True

    kwargs = _method_kwargs(
        create_data_field,
        {
            "profile": "smoke",
            "data_type_ref": "user",
            "name": "company",
            "type": "text",
            "execute": False,
        },
        execute=False,
    )

    assert kwargs == {
        "data_type_key": "user",
        "field_name": "company",
        "field_type": "text",
        "dry_run": True,
    }


def test_method_kwargs_maps_visual_and_workflow_aliases() -> None:
    def create_image(context_name: str, parent_name: str, name: str, source: str, dry_run: bool = False) -> bool:
        return True

    image_kwargs = _method_kwargs(
        create_image,
        {
            "context": "index",
            "parent": "root",
            "name": "im_logo",
            "image_url": "https://example.com/logo.png",
            "execute": False,
        },
        execute=False,
    )

    assert image_kwargs == {
        "context_name": "index",
        "parent_name": "root",
        "name": "im_logo",
        "source": "https://example.com/logo.png",
        "dry_run": True,
    }

    def create_workflow(context_name: str, element_name: str, event_type: str = "click", dry_run: bool = False) -> bool:
        return True

    workflow_kwargs = _method_kwargs(
        create_workflow,
        {
            "context": "index",
            "element_name": "Page",
            "event": "PageLoaded",
            "execute": False,
        },
        execute=False,
    )

    assert workflow_kwargs == {
        "context_name": "index",
        "element_name": "Page",
        "event_type": "PageLoaded",
        "dry_run": True,
    }
