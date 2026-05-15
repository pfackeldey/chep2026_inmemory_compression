#let poster(body) = {
  grid(
    columns: 1,
    rows: (10%, 1%, 85%, 1%, 3%),
    
    // Top = title row
    [
      #box(
        stroke: none,
        fill: white,
        height: 100%,
        width: 100%,
        inset: 1%,

        grid(
          columns: (10%, 80%, 10%),
          rows: 100%,
          stroke: none,
                
          // Left
          [
            #place(horizon+left, figure(image("princeton-logo.svg", width: auto, height: 220pt)))
          ],
          // Center
          [
            #place(horizon+center)[
                #text(size: 66pt, fill: black)[
                  *In-memory compression of Awkward Arrays with Coffea*
                  #v(15%, weak: true)
                ]
                #text(size: 42pt)[
                  Peter Elmer#super[1],
                  *Peter Fackeldey#super[1]*, 
                  Iason Krommydas#super[2], 
                  \
                  Princeton University#super[1],
                  Rice University#super[2]
                ]
              ]  
          ],
          [
            #place(horizon+right, figure(image("Rice_Shield_280_Blue.svg", width: auto, height: 210pt)))
          ]
        )
      )
    ],

    // Second row = horizontal line
    [
    #box(
      stroke: none,
      fill: white,
      height: 100%,
      width: 100%,
      inset: 1%,

      line(length: 100%, stroke: (paint: black, thickness: 4pt, cap: "round"))
      )
    ],

    // Middle = body
    [
      #box(
        height: 100%,    
        inset: 1%,
        fill: white,
        
        columns(2)[#body]
      )
    ],


    // Fourth row = horizontal line
    [
    #box(
      stroke: none,
      fill: white,
      height: 100%,
      width: 100%,
      inset: 1%,

      line(length: 100%, stroke: (paint: black, thickness: 4pt, cap: "round"))
      )
    ],
    
    // Bottom = footer
    [
      #box(
        stroke: none,
        fill: white,
        height: 100%,
        width: 100%,
        inset: 1%,

        grid(
          columns: (60%, 40%),
          rows: 100%,
          stroke: none,
          
          // Left
          [
            #place(horizon+left)[
              #text(size: 36pt)[
                *Acknowledgements:* This work was supported by the National Science Foundation under Cooperative Agreement PHY-2323298 and grant DE-SC0010103
              ]
            ]
          ],
          // Right
          [
            #place(horizon+right)[
              #text(size: 36pt)[
                *Contact:*\ #link("peter.fackeldey@cern.ch")[peter.fackeldey\@cern.ch]
              ]
            ]
          ]
        )
      )
    ]
  )
}