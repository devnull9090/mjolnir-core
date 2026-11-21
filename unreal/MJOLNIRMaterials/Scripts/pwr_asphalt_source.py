from pathlib import Path


def shared_corners(source, first, last, cell, values):
    start = source.index(first)
    end = source.index(last, start)
    grid = Path(__file__).with_name("pwr_surface_grid.ush").read_text()
    return source[:start] + grid.replace("GRID_CELL", cell).replace("GRID_VALUES", values) + source[end:]


def wearing_course(revision):
    """Assemble the road material for the requested native playtest revision."""
    scripts = Path(__file__).resolve().parent
    source = (scripts / "pwr_weathered_asphalt.ush").read_text().strip()
    finish_revision = 31 if revision >= 31 else 30
    if revision >= 27:
        start = source.index("        // A physical crushed-mineral")
        end = source.index("        // Independently scaled campaign", start)
        mineral_file = f"pwr_asphalt_mineral{finish_revision}.ush" if revision >= 30 else "pwr_asphalt_stochastic_chip.ush"
        chip = (scripts / mineral_file).read_text().rstrip()
        source = source[:start] + chip + "\n\n" + source[end:]
    if revision >= 30:
        start = source.index("        // Keep the asphalt centred")
        end = source.index("        n *= rsqrt", start)
        grade = """        float edgeMetres=side+raggedEdge+.48*(chip.a-.476)+.46*(chip.r-.401);
        float course=1.-smoothstep(8.46,8.88,edgeMetres);
        float apron=(1.-smoothstep(10.1,13.1,edgeMetres))*cover;
        float influence=saturate(mainRoute*apron);"""
        if revision >= 31:
            grade = """        float fault=clamp((gravelValue-.113)*2.4+(dust-.5)*.34,-.28,.37);
        float edgeMetres=side+raggedEdge+fault+.42*(chip.a-.476);
        float course=1.-smoothstep(8.51,8.80,edgeMetres);
        float apron=(1.-smoothstep(10.1,13.1,edgeMetres))*cover;
        float influence=saturate(mainRoute*apron);"""
        course = (scripts / f"pwr_asphalt_course{finish_revision}.ush").read_text().rstrip()
        course = shared_corners(course, "        // Insert shared integer corner values.",
                                "        float field =", "washCell", "values")
        shoulder = (scripts / f"pwr_asphalt_shoulder{finish_revision}.ush").read_text().rstrip()
        return source[:start] + "\n".join((grade, course, shoulder, "")) + source[end:]
    if revision >= 26:
        start = source.index("        // Keep the asphalt centred")
        end = source.index("        float2 n = lerp", start)
        if revision >= 29:
            filename = "pwr_asphalt_finish29.ush"
        elif revision >= 27:
            filename = "pwr_asphalt_finish27.ush"
        else:
            filename = "pwr_asphalt_aggregate_finish.ush"
        finish = (scripts / filename).read_text().rstrip()
        if revision >= 29:
            finish = shared_corners(finish, "        // Insert shared integer corner values.",
                                    "        float field =", "washCell", "values")
        elif revision >= 28:
            finish = shared_corners(finish, "        float4 values =", "        float field =", "washCell", "values")
            # The registered game view places the dry wearing course in deep
            # shade. Use a warmer, less contrasty dust layer over the binder.
            finish = finish.replace("field+.17*(dust-.5)+.13*drift-.15*wheel",
                                    ".72*field+.28*dust+.08*drift-.10*wheel")
            finish = finish.replace("float3(.054,.055,.054),float3(.096,.091,.080)",
                                    "float3(.058,.059,.057),float3(.092,.088,.079)")
            finish = finish.replace("float3(1.08,1.25,1.71)", "float3(1.28,1.45,1.91)")
            finish = finish.replace("        float dash =", """        asphalt *= clamp(1.+1.8*(chipValue-.388)+.13*(mineralGrain-.38),.82,1.20);
        float abrasion = .52*sin(2.7*rotated.x+.54*sin(1.9*rotated.y))
                       + .38*sin(1.71*rotated.y+.60*sin(.97*rotated.x))+.25*(dust-.5);
        float dash =""").replace("paint*.27", "paint*.25*smoothstep(-.05,.35,abrasion)")
            finish = finish.replace("(variation.xy-.5)*.25", "(variation.xy-.5)*.54")
            finish = finish.replace("                float radius =", """                float rotSin, rotCos;
                sincos(6.2831853*variation.x,rotSin,rotCos);
                facet = mul(float2x2(rotCos,-rotSin,rotSin,rotCos),facet);
                float radius =""")
            finish = finish.replace("pebble*bed*pebbleVisibility",
                                    "pebble*bed*pebbleVisibility*smoothstep(.22,.65,variation.y+.40*(field-.5))")
            finish += "\n        shoulder *= float3(.81,.82,.88);"
        source = source[:start] + finish + "\n" + source[end:]
    return source
